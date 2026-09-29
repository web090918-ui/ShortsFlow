import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.acquisition import (
    AcquisitionError,
    ApifyTitanProvider,
    SubtitlesUnavailableError,
    VideoAcquisitionProvider,
)


OPENAI_FILE_LIMIT_BYTES = 25 * 1024 * 1024


class TranscriptProcessingError(RuntimeError):
    pass


class TranscriptUnavailableError(TranscriptProcessingError):
    pass


class CaptionsUnavailableError(TranscriptProcessingError):
    """The source has no caption track the caption provider can return."""


class TranscriptSegment(BaseModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    text: str = Field(min_length=1)


class TranscriptResult(BaseModel):
    provider: Literal["apify_titan", "openai_whisper"]
    language: str | None
    is_generated: bool
    source_start_seconds: float
    source_end_seconds: float
    segments: list[TranscriptSegment]
    full_text: str


class CaptionProvider(Protocol):
    def fetch(
        self, source_url: str, *, language: str | None = None
    ) -> TranscriptResult: ...


class AudioAcquirer(Protocol):
    def acquire(self, source_url: str, *, destination: Path) -> None: ...


class AudioExtractor(Protocol):
    def extract(
        self,
        media_path: Path,
        audio_path: Path,
        *,
        start_seconds: float | None = None,
        end_seconds: float | None = None,
    ) -> None: ...


class SpeechToTextProvider(Protocol):
    def transcribe(
        self, audio_path: Path, *, language: str | None = None
    ) -> TranscriptResult: ...


def _clean_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


_TIMESTAMP = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")


def _parse_timestamp(value: str) -> float | None:
    match = _TIMESTAMP.search(value)
    if match is None:
        return None
    hours, minutes, seconds, fraction = match.groups()
    return (
        int(hours or 0) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(fraction.ljust(3, "0")) / 1000
    )


def _parse_json3(payload: dict[str, Any]) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for event in payload.get("events") or []:
        if not isinstance(event, dict):
            continue
        start_ms = event.get("tStartMs")
        duration_ms = event.get("dDurationMs")
        text = "".join(
            seg.get("utf8", "")
            for seg in event.get("segs") or []
            if isinstance(seg, dict) and isinstance(seg.get("utf8"), str)
        )
        text = " ".join(text.split())
        if (
            not isinstance(start_ms, (int, float))
            or not isinstance(duration_ms, (int, float))
            or duration_ms <= 0
            or not text
        ):
            continue
        segments.append(
            TranscriptSegment(
                start_seconds=start_ms / 1000,
                end_seconds=(start_ms + duration_ms) / 1000,
                text=text,
            )
        )
    return segments


def _parse_cue_text(text: str) -> list[TranscriptSegment]:
    """Parse WebVTT or SRT cues; both share the ``start --> end`` line."""
    segments: list[TranscriptSegment] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
    for block in blocks:
        lines = [line for line in block.split("\n") if line.strip()]
        timing_index = next(
            (index for index, line in enumerate(lines) if "-->" in line), None
        )
        if timing_index is None:
            continue
        start_raw, _, end_raw = lines[timing_index].partition("-->")
        start = _parse_timestamp(start_raw)
        end = _parse_timestamp(end_raw)
        cue_text = " ".join(
            re.sub(r"<[^>]+>", "", line).strip() for line in lines[timing_index + 1 :]
        ).strip()
        if start is None or end is None or end <= start or not cue_text:
            continue
        segments.append(
            TranscriptSegment(start_seconds=start, end_seconds=end, text=cue_text)
        )
    return segments


def parse_caption_text(text: str) -> list[TranscriptSegment]:
    """Turn json3, WebVTT, or SRT caption text into timestamped segments."""
    stripped = text.lstrip("﻿").strip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise TranscriptProcessingError(
                "자막 파일을 해석하지 못했습니다."
            ) from exc
        return _parse_json3(payload) if isinstance(payload, dict) else []
    return _parse_cue_text(stripped)


class TitanCaptionProvider:
    """Caption-first step backed by the Apify Titan subtitles mode."""

    def __init__(self, provider: ApifyTitanProvider) -> None:
        self._provider = provider

    def fetch(
        self, source_url: str, *, language: str | None = None
    ) -> TranscriptResult:
        requested = (language or "ko").split("-", 1)[0]
        try:
            text = self._provider.fetch_subtitles(source_url, language=requested)
        except SubtitlesUnavailableError as exc:
            raise CaptionsUnavailableError(str(exc)) from exc
        segments = parse_caption_text(text)
        if not segments:
            raise CaptionsUnavailableError("YouTube 영상에 사용할 수 있는 자막이 없습니다.")
        return TranscriptResult(
            provider="apify_titan",
            language=requested,
            is_generated=False,
            source_start_seconds=0,
            source_end_seconds=max(segment.end_seconds for segment in segments),
            segments=segments,
            full_text=" ".join(segment.text for segment in segments),
        )


class ProviderAudioAcquirer:
    """Fetch the full source through the shared acquisition provider."""

    def __init__(self, provider: VideoAcquisitionProvider) -> None:
        self._provider = provider

    def acquire(self, source_url: str, *, destination: Path) -> None:
        try:
            self._provider.acquire(source_url, destination=destination)
        except AcquisitionError as exc:
            raise TranscriptProcessingError(str(exc)) from exc


class FfmpegAudioExtractor:
    def extract(
        self,
        media_path: Path,
        audio_path: Path,
        *,
        start_seconds: float | None = None,
        end_seconds: float | None = None,
    ) -> None:
        executable = shutil.which("ffmpeg")
        if executable is None:
            raise TranscriptProcessingError("FFmpeg 실행 파일을 찾을 수 없습니다.")
        command = [executable, "-nostdin", "-hide_banner", "-loglevel", "error"]
        if start_seconds is not None:
            command += ["-ss", f"{start_seconds:.3f}"]
        command += ["-i", str(media_path)]
        if start_seconds is not None and end_seconds is not None:
            command += ["-t", f"{end_seconds - start_seconds:.3f}"]
        command += [
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "32k",
            "-f",
            "mp3",
            "-y",
            str(audio_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=300)
        except subprocess.TimeoutExpired as exc:
            raise TranscriptProcessingError("오디오 추출 시간이 초과되었습니다.") from exc
        except subprocess.CalledProcessError as exc:
            raise TranscriptProcessingError("영상에서 오디오를 추출하지 못했습니다.") from exc
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            raise TranscriptProcessingError("추출된 오디오가 비어 있습니다.")
        if audio_path.stat().st_size > OPENAI_FILE_LIMIT_BYTES:
            raise TranscriptProcessingError(
                "추출된 오디오가 STT 업로드 제한인 25MB를 초과했습니다."
            )


class OpenAIWhisperProvider:
    def __init__(self, client: Any, *, model: str = "whisper-1") -> None:
        self._client = client
        self._model = model

    def transcribe(
        self, audio_path: Path, *, language: str | None = None
    ) -> TranscriptResult:
        try:
            with audio_path.open("rb") as audio:
                request: dict[str, Any] = {
                    "file": audio,
                    "model": self._model,
                    "response_format": "verbose_json",
                    "timestamp_granularities": ["segment"],
                }
                if language is not None:
                    request["language"] = language.split("-", 1)[0]
                response = self._client.audio.transcriptions.create(
                    **request
                )
        except Exception as exc:
            raise TranscriptProcessingError(
                "STT 처리에 실패했습니다. 잠시 후 다시 시도해 주세요."
            ) from exc
        payload = response.model_dump() if hasattr(response, "model_dump") else response
        if not isinstance(payload, dict):
            raise TranscriptProcessingError("STT 서비스가 올바르지 않은 응답을 반환했습니다.")
        raw_segments = payload.get("segments")
        if not isinstance(raw_segments, list):
            raise TranscriptProcessingError("STT 타임스탬프를 받지 못했습니다.")
        segments: list[TranscriptSegment] = []
        for raw in raw_segments:
            if not isinstance(raw, dict):
                continue
            start = raw.get("start")
            end = raw.get("end")
            text = _clean_text(raw.get("text"))
            if (
                not isinstance(start, (int, float))
                or not isinstance(end, (int, float))
                or start < 0
                or end <= start
                or not text
            ):
                continue
            segments.append(
                TranscriptSegment(
                    start_seconds=float(start),
                    end_seconds=float(end),
                    text=text,
                )
            )
        if not segments:
            raise TranscriptProcessingError("음성에서 텍스트를 인식하지 못했습니다.")
        return TranscriptResult(
            provider="openai_whisper",
            language=payload.get("language")
            if isinstance(payload.get("language"), str)
            else None,
            is_generated=True,
            source_start_seconds=0,
            source_end_seconds=max(segment.end_seconds for segment in segments),
            segments=segments,
            full_text=" ".join(segment.text for segment in segments),
        )


class TranscriptProcessor:
    def __init__(
        self,
        caption_provider: CaptionProvider,
        *,
        audio_acquirer: AudioAcquirer | None = None,
        audio_extractor: AudioExtractor | None = None,
        stt_provider: SpeechToTextProvider | None = None,
    ) -> None:
        self._caption_provider = caption_provider
        self._audio_acquirer = audio_acquirer
        self._audio_extractor = audio_extractor
        self._stt_provider = stt_provider

    @staticmethod
    def _select_range(
        transcript: TranscriptResult,
        *,
        start_seconds: float,
        end_seconds: float,
        relative: bool,
    ) -> TranscriptResult:
        offset = start_seconds if relative else 0
        selected: list[TranscriptSegment] = []
        for segment in transcript.segments:
            start = segment.start_seconds + offset
            end = segment.end_seconds + offset
            if end <= start_seconds or start >= end_seconds:
                continue
            selected.append(
                TranscriptSegment(
                    start_seconds=max(start, start_seconds),
                    end_seconds=min(end, end_seconds),
                    text=segment.text,
                )
            )
        if not selected:
            raise TranscriptUnavailableError(
                "선택한 구간에서 인식 가능한 음성이나 자막을 찾지 못했습니다."
            )
        return TranscriptResult(
            provider=transcript.provider,
            language=transcript.language,
            is_generated=transcript.is_generated,
            source_start_seconds=start_seconds,
            source_end_seconds=end_seconds,
            segments=selected,
            full_text=" ".join(segment.text for segment in selected),
        )

    def process(
        self,
        source_url: str,
        *,
        start_seconds: float,
        end_seconds: float,
        language: str | None = None,
    ) -> TranscriptResult:
        try:
            captions = self._caption_provider.fetch(source_url, language=language)
            return self._select_range(
                captions,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                relative=False,
            )
        except (CaptionsUnavailableError, TranscriptUnavailableError):
            if (
                self._audio_acquirer is None
                or self._audio_extractor is None
                or self._stt_provider is None
            ):
                raise TranscriptProcessingError(
                    "YouTube 자막이 없으며 OpenAI STT가 설정되지 않았습니다."
                )
            # The acquirer delivers the whole source; FFmpeg trims the audio to the
            # selected range so Whisper timestamps are relative to start_seconds.
            with tempfile.TemporaryDirectory(
                prefix="shortsflow-transcript-", ignore_cleanup_errors=True
            ) as temp:
                temp_path = Path(temp)
                media_path = temp_path / "source.mp4"
                audio_path = temp_path / "audio.mp3"
                self._audio_acquirer.acquire(source_url, destination=media_path)
                self._audio_extractor.extract(
                    media_path,
                    audio_path,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                )
                transcript = self._stt_provider.transcribe(
                    audio_path, language=language
                )
            return self._select_range(
                transcript,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                relative=True,
            )
