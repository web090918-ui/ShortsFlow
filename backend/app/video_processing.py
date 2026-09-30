"""FFmpeg-backed editing boundary for the manual-range Short pipeline.

Acquisition providers deliver a source file; this module owns trimming and the
9:16 conversion so the two responsibilities stay separable.
"""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920
FFMPEG_TIMEOUT_SECONDS = 15 * 60


class VideoProcessingError(RuntimeError):
    """FFmpeg or ffprobe could not complete the requested edit."""


@dataclass(frozen=True)
class VideoInfo:
    duration_seconds: float
    width: int | None
    height: int | None


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
    ) -> None: ...


def _escape_filter_path(path: Path) -> str:
    """Quote a filename for use inside an FFmpeg filtergraph option."""
    value = path.as_posix()
    for char in ("\\", "'", ":", ",", "[", "]", ";"):
        value = value.replace(char, "\\" + char)
    return value


def _vertical_filter(subtitles_path: Path | None = None) -> str:
    # Scale so the frame covers 1080x1920, then center crop. A 1920x1080 source
    # becomes 3413x1920 before the crop, which is the "scale + center crop" MVP rule.
    chain = (
        f"scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={SHORT_WIDTH}:{SHORT_HEIGHT},setsar=1"
    )
    if subtitles_path is not None:
        # Burn the template-styled ASS file after the crop so positions match 1080x1920.
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
        for stream in payload.get("streams") or []:
            if isinstance(stream, dict) and stream.get("codec_type") == "video":
                width = stream.get("width") if isinstance(stream.get("width"), int) else None
                height = (
                    stream.get("height") if isinstance(stream.get("height"), int) else None
                )
                break
        return VideoInfo(duration_seconds=duration, width=width, height=height)

    def _encode(
        self,
        input_path: Path,
        output_path: Path,
        *,
        start_seconds: float | None = None,
        end_seconds: float | None = None,
        video_filter: str | None = None,
    ) -> None:
        command = [self._executable("ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error"]
        if start_seconds is not None:
            # Input seeking keeps the trim fast; re-encoding below keeps it frame-accurate.
            command += ["-ss", f"{start_seconds:.3f}"]
        command += ["-i", str(input_path)]
        if start_seconds is not None and end_seconds is not None:
            command += ["-t", f"{end_seconds - start_seconds:.3f}"]
        if video_filter is not None:
            command += ["-vf", video_filter]
        command += [
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
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
    ) -> None:
        # One encode pass instead of trim followed by convert: same result, half the time.
        self._encode(
            input_path,
            output_path,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            video_filter=_vertical_filter(subtitles_path),
        )
