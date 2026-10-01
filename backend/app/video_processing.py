"""FFmpeg-backed editing boundary for the manual-range Short pipeline.

Acquisition providers deliver a source file; this module owns trimming and the
9:16 conversion so the two responsibilities stay separable.
"""

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.templates import RenderLayout, STAGE_PICTURE_HEIGHT


SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920
# Product Shorts picture box (see captions.PRODUCT_PICTURE_TOP/BOTTOM).
PRODUCT_BOX_WIDTH = 1080
PRODUCT_BOX_HEIGHT = 900
PRODUCT_BOX_TOP = 330
FFMPEG_TIMEOUT_SECONDS = 15 * 60
# Silence removal: anything quieter than this for at least this long is a pause.
SILENCE_NOISE_DB = -35
SILENCE_MIN_SECONDS = 0.6
# Breathing room kept on both sides of every cut so words are not clipped.
SILENCE_PADDING_SECONDS = 0.12
# A kept stretch shorter than this merges with its neighbour instead of a jump cut.
MIN_SPEECH_SEGMENT_SECONDS = 0.4
_SILENCE_START = re.compile(r"silence_start:\s*(-?[0-9.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*(-?[0-9.]+)")


class VideoProcessingError(RuntimeError):
    """FFmpeg or ffprobe could not complete the requested edit."""


@dataclass(frozen=True)
class VideoInfo:
    duration_seconds: float
    width: int | None
    height: int | None
    has_audio: bool = True


Segment = tuple[float, float]


def speech_segments(
    silences: list[Segment],
    *,
    start_seconds: float,
    end_seconds: float,
    padding_seconds: float = SILENCE_PADDING_SECONDS,
    min_segment_seconds: float = MIN_SPEECH_SEGMENT_SECONDS,
) -> list[Segment]:
    """The parts of [start, end] to keep once the detected silences are cut out.

    Each silence is shrunk by ``padding_seconds`` on both sides so speech never gets
    clipped; a silence too short to survive that shrink is not cut at all.
    """
    cuts: list[Segment] = []
    for raw_start, raw_end in sorted(silences):
        cut_start = max(start_seconds, raw_start + padding_seconds)
        cut_end = min(end_seconds, raw_end - padding_seconds)
        if cut_end - cut_start <= 0:
            continue
        if cuts and cut_start <= cuts[-1][1]:
            cuts[-1] = (cuts[-1][0], max(cuts[-1][1], cut_end))
        else:
            cuts.append((cut_start, cut_end))
    kept: list[Segment] = []
    cursor = start_seconds
    for cut_start, cut_end in cuts:
        if cut_start - cursor >= min_segment_seconds:
            kept.append((cursor, cut_start))
        elif kept:
            # Too short to stand alone: keep it (and the silence) attached to the previous part.
            kept[-1] = (kept[-1][0], cut_start)
        elif cut_start > cursor:
            # Leading sliver before the first silence: keep it rather than start on a cut.
            kept.append((cursor, cut_start))
        cursor = cut_end
    if end_seconds - cursor >= min_segment_seconds or not kept:
        kept.append((cursor, end_seconds))
    elif end_seconds > cursor:
        kept[-1] = (kept[-1][0], end_seconds)
    return [(round(s, 3), round(e, 3)) for s, e in kept if e > s]


def segments_duration(segments: list[Segment]) -> float:
    return round(sum(end - start for start, end in segments), 3)


def parse_silences(stderr: str, *, offset_seconds: float = 0.0) -> list[Segment]:
    """Pair silencedetect's start/end log lines into absolute (start, end) tuples."""
    starts = [float(m.group(1)) for m in _SILENCE_START.finditer(stderr)]
    ends = [float(m.group(1)) for m in _SILENCE_END.finditer(stderr)]
    pairs: list[Segment] = []
    for index, start in enumerate(starts):
        end = ends[index] if index < len(ends) else None
        if end is None:
            continue  # silence running to the end of the probed range: nothing to cut after speech
        if end > start:
            pairs.append((offset_seconds + max(0.0, start), offset_seconds + end))
    return pairs


class VideoProcessor(Protocol):
    def probe(self, media_path: Path) -> VideoInfo: ...

    def trim(
        self,
        input_path: Path,
        output_path: Path,
        *,
        start_seconds: float,
        end_seconds: float,
        max_height: int | None = None,
    ) -> None: ...

    def convert_to_vertical(self, input_path: Path, output_path: Path) -> None: ...

    def trim_to_vertical(
        self,
        input_path: Path,
        output_path: Path,
        *,
        start_seconds: float,
        end_seconds: float,
        subtitles_path: Path | None = None,
        layout: RenderLayout = RenderLayout.FILL,
        stage_color: str = "#000000",
        keep_segments: list[Segment] | None = None,
        picture_height: int = STAGE_PICTURE_HEIGHT,
    ) -> None: ...

    def detect_silences(
        self, media_path: Path, *, start_seconds: float, end_seconds: float
    ) -> list[Segment]: ...


def _escape_filter_path(path: Path) -> str:
    """Quote a filename for use inside an FFmpeg filtergraph option."""
    value = path.as_posix()
    for char in ("\\", "'", ":", ",", "[", "]", ";"):
        value = value.replace(char, "\\" + char)
    return value


def _vertical_filter(
    subtitles_path: Path | None = None,
    layout: RenderLayout = RenderLayout.FILL,
    stage_color: str = "#000000",
    picture_height: int = STAGE_PICTURE_HEIGHT,
) -> str:
    if layout == RenderLayout.STAGE:
        # Fill the stage picture band edge to edge, cropping centrally as needed.
        # Keep the headline and caption bands outside the picture.
        color = "0x" + stage_color.lstrip("#")
        chain = (
            f"scale={SHORT_WIDTH}:{picture_height}:force_original_aspect_ratio=increase,"
            f"crop={SHORT_WIDTH}:{picture_height},"
            f"pad={SHORT_WIDTH}:{SHORT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:{color},setsar=1"
        )
    elif layout == RenderLayout.FIT:
        # Keep the whole source frame (so its own captions and framing survive) and
        # fill the rest of the 9:16 canvas with a blurred, enlarged copy of itself.
        # The background is blurred at a quarter size: same look, far less work.
        chain = (
            "split[bg][fg];"
            f"[bg]scale={SHORT_WIDTH // 4}:{SHORT_HEIGHT // 4}:force_original_aspect_ratio=increase,"
            f"crop={SHORT_WIDTH // 4}:{SHORT_HEIGHT // 4},boxblur=10:2,"
            f"scale={SHORT_WIDTH}:{SHORT_HEIGHT},setsar=1[bgs];"
            f"[fg]scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=decrease,setsar=1[fgs];"
            "[bgs][fgs]overlay=(W-w)/2:(H-h)/2"
        )
    else:
        # Scale so the frame covers 1080x1920, then center crop. A 1920x1080 source
        # becomes 3413x1920 before the crop, which is the "scale + center crop" MVP rule.
        chain = (
            f"scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={SHORT_WIDTH}:{SHORT_HEIGHT},setsar=1"
        )
    if subtitles_path is not None:
        # Burn the template-styled ASS file last so positions match 1080x1920.
        chain += f",subtitles=filename='{_escape_filter_path(subtitles_path)}'"
    return chain


class FfmpegVideoProcessor:
    def __init__(self, *, timeout_seconds: float = FFMPEG_TIMEOUT_SECONDS) -> None:
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def _executable(name: str) -> str:
        executable = shutil.which(name)
        if executable is None:
            raise VideoProcessingError(f"{name} 실행 파일을 찾을 수 없습니다.")
        return executable

    def probe(self, media_path: Path) -> VideoInfo:
        command = [
            self._executable("ffprobe"),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(media_path),
        ]
        try:
            completed = subprocess.run(
                command, check=True, capture_output=True, timeout=120
            )
            payload = json.loads(completed.stdout.decode("utf-8"))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise VideoProcessingError("원본 영상 정보를 읽지 못했습니다.") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise VideoProcessingError("원본 영상 정보를 해석하지 못했습니다.") from exc

        duration_raw = (payload.get("format") or {}).get("duration")
        try:
            duration = float(duration_raw)
        except (TypeError, ValueError) as exc:
            raise VideoProcessingError("원본 영상 길이를 확인하지 못했습니다.") from exc
        if duration <= 0:
            raise VideoProcessingError("원본 영상 길이를 확인하지 못했습니다.")

        width = height = None
        has_audio = False
        for stream in payload.get("streams") or []:
            if not isinstance(stream, dict):
                continue
            if stream.get("codec_type") == "audio":
                has_audio = True
            if stream.get("codec_type") == "video" and width is None:
                width = stream.get("width") if isinstance(stream.get("width"), int) else None
                height = (
                    stream.get("height") if isinstance(stream.get("height"), int) else None
                )
        return VideoInfo(duration_seconds=duration, width=width, height=height, has_audio=has_audio)

    def detect_silences(
        self, media_path: Path, *, start_seconds: float, end_seconds: float
    ) -> list[Segment]:
        """Absolute (start, end) pauses inside the range, from FFmpeg's silencedetect."""
        command = [
            self._executable("ffmpeg"),
            "-nostdin",
            "-hide_banner",
            "-nostats",
            "-ss",
            f"{start_seconds:.3f}",
            "-t",
            f"{end_seconds - start_seconds:.3f}",
            "-i",
            str(media_path),
            "-vn",
            "-af",
            f"silencedetect=noise={SILENCE_NOISE_DB}dB:d={SILENCE_MIN_SECONDS}",
            "-f",
            "null",
            "-",
        ]
        try:
            completed = subprocess.run(
                command, check=True, capture_output=True, timeout=self._timeout_seconds
            )
        except subprocess.TimeoutExpired as exc:
            raise VideoProcessingError("무음 구간 분석 시간이 초과되었습니다.") from exc
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.decode("utf-8", errors="replace").strip() if exc.stderr else ""
            raise VideoProcessingError(
                "무음 구간을 분석하지 못했습니다." + (f" ({detail[:200]})" if detail else "")
            ) from exc
        stderr = completed.stderr.decode("utf-8", errors="replace") if completed.stderr else ""
        return parse_silences(stderr, offset_seconds=start_seconds)

    def _encode(
        self,
        input_path: Path,
        output_path: Path,
        *,
        start_seconds: float | None = None,
        end_seconds: float | None = None,
        video_filter: str | None = None,
        filter_complex: str | None = None,
    ) -> None:
        command = [self._executable("ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error"]
        if start_seconds is not None:
            # Input seeking keeps the trim fast; re-encoding below keeps it frame-accurate.
            command += ["-ss", f"{start_seconds:.3f}"]
        command += ["-i", str(input_path)]
        if start_seconds is not None and end_seconds is not None and filter_complex is None:
            command += ["-t", f"{end_seconds - start_seconds:.3f}"]
        if filter_complex is not None:
            # The graph trims, joins and reframes in one pass; it labels its outputs.
            command += ["-filter_complex", filter_complex, "-map", "[vout]", "-map", "[aout]"]
        else:
            if video_filter is not None:
                command += ["-vf", video_filter]
            command += ["-map", "0:v:0", "-map", "0:a:0?"]
        command += [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            "-y",
            str(output_path),
        ]
        try:
            subprocess.run(
                command, check=True, capture_output=True, timeout=self._timeout_seconds
            )
        except subprocess.TimeoutExpired as exc:
            raise VideoProcessingError("영상 편집 시간이 초과되었습니다.") from exc
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.decode("utf-8", errors="replace").strip() if exc.stderr else ""
            raise VideoProcessingError(
                "영상을 편집하지 못했습니다." + (f" ({detail[:200]})" if detail else "")
            ) from exc
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise VideoProcessingError("편집된 영상이 비어 있습니다.")

    def trim(
        self,
        input_path: Path,
        output_path: Path,
        *,
        start_seconds: float,
        end_seconds: float,
        max_height: int | None = None,
    ) -> None:
        # max_height produces a lower-resolution analysis proxy without changing aspect.
        video_filter = (
            f"scale=-2:'min(ih,{max_height})'" if max_height is not None else None
        )
        self._encode(
            input_path,
            output_path,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            video_filter=video_filter,
        )

    def convert_to_vertical(self, input_path: Path, output_path: Path) -> None:
        self._encode(input_path, output_path, video_filter=_vertical_filter())

    def trim_to_vertical(
        self,
        input_path: Path,
        output_path: Path,
        *,
        start_seconds: float,
        end_seconds: float,
        subtitles_path: Path | None = None,
        layout: RenderLayout = RenderLayout.FILL,
        stage_color: str = "#000000",
        keep_segments: list[Segment] | None = None,
        picture_height: int = STAGE_PICTURE_HEIGHT,
    ) -> None:
        vertical = _vertical_filter(subtitles_path, layout, stage_color, picture_height)
        if keep_segments and keep_segments != [(start_seconds, end_seconds)]:
            # Jump-cut render: keep only the listed stretches (absolute times), joined in
            # order, then reframe. Input seeking to the range start keeps decoding short,
            # so trim times are relative to it. Subtitles were already retimed to match.
            parts = []
            for index, (seg_start, seg_end) in enumerate(keep_segments):
                rel_start = max(0.0, seg_start - start_seconds)
                rel_end = max(rel_start, seg_end - start_seconds)
                parts.append(
                    f"[0:v]trim=start={rel_start:.3f}:end={rel_end:.3f},setpts=PTS-STARTPTS[v{index}];"
                    f"[0:a]atrim=start={rel_start:.3f}:end={rel_end:.3f},asetpts=PTS-STARTPTS[a{index}]"
                )
            inputs = "".join(f"[v{i}][a{i}]" for i in range(len(keep_segments)))
            graph = (
                ";".join(parts)
                + f";{inputs}concat=n={len(keep_segments)}:v=1:a=1[vc][aout];"
                + f"[vc]{vertical}[vout]"
            )
            self._encode(
                input_path,
                output_path,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                filter_complex=graph,
            )
            return
        # One encode pass instead of trim followed by convert: same result, half the time.
        self._encode(
            input_path,
            output_path,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            video_filter=vertical,
        )

    def _run(self, command: list[str], *, failure: str) -> None:
        try:
            subprocess.run(
                command, check=True, capture_output=True, timeout=self._timeout_seconds
            )
        except subprocess.TimeoutExpired as exc:
            raise VideoProcessingError("영상 편집 시간이 초과되었습니다.") from exc
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.decode("utf-8", errors="replace").strip() if exc.stderr else ""
            raise VideoProcessingError(
                failure + (f" ({detail[:200]})" if detail else "")
            ) from exc

    def make_silence(self, destination: Path, *, seconds: float) -> None:
        command = [
            self._executable("ffmpeg"),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=24000:cl=mono",
            "-t",
            f"{seconds:.3f}",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "48k",
            "-y",
            str(destination),
        ]
        self._run(command, failure="무음 구간을 만들지 못했습니다.")

    def concat_audio(self, parts: list[Path], output_path: Path) -> None:
        """Join MP3 clips into one AAC track, re-encoding so mixed encoders are safe."""
        if not parts:
            raise VideoProcessingError("이어 붙일 음성이 없습니다.")
        command = [self._executable("ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error"]
        for part in parts:
            command += ["-i", str(part)]
        inputs = "".join(f"[{index}:a:0]" for index in range(len(parts)))
        command += [
            "-filter_complex",
            f"{inputs}concat=n={len(parts)}:v=0:a=1[a]",
            "-map",
            "[a]",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-y",
            str(output_path),
        ]
        self._run(command, failure="음성을 이어 붙이지 못했습니다.")
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise VideoProcessingError("이어 붙인 음성이 비어 있습니다.")

    def compose_product_short(
        self,
        image_paths: "Path | list[Path]",
        audio_path: Path,
        output_path: Path,
        *,
        duration_seconds: float,
        subtitles_path: Path | None = None,
        stage_color: str = "#000000",
        fps: int = 30,
    ) -> None:
        """Product pictures -> 1080x1920 clip on the template's stage colour.

        Each picture fills a 1080x900 box in turn (equal shares of the clip) with a
        slow zoom, the box sits at y=330 under the headline band, template text comes
        from the ASS file, and the narration is the audio track.
        """
        images = [image_paths] if isinstance(image_paths, Path) else list(image_paths)
        if not images:
            raise VideoProcessingError("상품 이미지가 없습니다.")
        color = "0x" + stage_color.lstrip("#")
        total_frames = max(len(images), int(round(duration_seconds * fps)))
        share = total_frames // len(images)
        chain: list[str] = []
        for index in range(len(images)):
            frames = share if index < len(images) - 1 else total_frames - share * (len(images) - 1)
            chain.append(
                f"[{index}:v]scale={PRODUCT_BOX_WIDTH}:{PRODUCT_BOX_HEIGHT}:force_original_aspect_ratio=decrease,"
                "scale=trunc(iw/2)*2:trunc(ih/2)*2,"
                f"pad={PRODUCT_BOX_WIDTH}:{PRODUCT_BOX_HEIGHT}:(ow-iw)/2:(oh-ih)/2:{color},"
                f"zoompan=z='1+0.10*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={frames}:s={PRODUCT_BOX_WIDTH}x{PRODUCT_BOX_HEIGHT}:fps={fps}[s{index}]"
            )
        inputs = "".join(f"[s{index}]" for index in range(len(images)))
        chain.append(f"{inputs}concat=n={len(images)}:v=1:a=0[pic]")
        tail = (
            f"[pic]pad={SHORT_WIDTH}:{SHORT_HEIGHT}:0:{PRODUCT_BOX_TOP}:{color},setsar=1"
        )
        if subtitles_path is not None:
            tail += f",subtitles=filename='{_escape_filter_path(subtitles_path)}'"
        chain.append(tail + "[v]")
        command = [self._executable("ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error"]
        for image in images:
            command += ["-framerate", str(fps), "-i", str(image)]
        command += [
            "-i",
            str(audio_path),
            "-filter_complex",
            ";".join(chain),
            "-map",
            "[v]",
            "-map",
            f"{len(images)}:a:0",
            "-t",
            f"{duration_seconds:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            "-y",
            str(output_path),
        ]
        self._run(command, failure="상품 쇼츠를 합성하지 못했습니다.")
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise VideoProcessingError("합성된 영상이 비어 있습니다.")
