import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from app.tunelio import TunelioClient, TunelioTranscriptNotFoundError


OPENAI_FILE_LIMIT_BYTES = 25 * 1024 * 1024
MAX_MEDIA_BYTES = 750 * 1024 * 1024


class TranscriptProcessingError(RuntimeError):
    pass


class TranscriptUnavailableError(TranscriptProcessingError):
    pass


class TranscriptSegment(BaseModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    text: str = Field(min_length=1)


class TranscriptResult(BaseModel):
    provider: Literal["tunelio", "openai_whisper"]
    language: str | None
    is_generated: bool
    source_start_seconds: float
    source_end_seconds: float
    segments: list[TranscriptSegment]
    full_text: str


class CaptionProvider(Protocol):
    def fetch(self, source_url: str) -> TranscriptResult: ...


class AudioAcquirer(Protocol):
    def acquire(
        self,
        source_url: str,
        *,
        start_seconds: float,
        end_seconds: float,
        destination: Path,
    ) -> None: ...


class AudioExtractor(Protocol):
    def extract(self, media_path: Path, audio_path: Path) -> None: ...


class SpeechToTextProvider(Protocol):
    def transcribe(self, audio_path: Path) -> TranscriptResult: ...


def _clean_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


class TunelioCaptionProvider:
    def __init__(self, client: TunelioClient) -> None:
        self._client = client

    def fetch(self, source_url: str) -> TranscriptResult:
        payload = self._client.transcript(source_url)
        raw_segments = payload.get("segments")
        if not isinstance(raw_segments, list):
            raise TranscriptProcessingError(
                "자막 서비스가 올바르지 않은 응답을 반환했습니다."
            )
        segments: list[TranscriptSegment] = []
        for raw in raw_segments:
            if not isinstance(raw, dict):
                continue
            start = raw.get("start")
            duration = raw.get("duration")
            text = _clean_text(raw.get("text"))
            if (
                not isinstance(start, (int, float))
                or not isinstance(duration, (int, float))
                or start < 0
                or duration <= 0
                or not text
            ):
                continue
            segments.append(
                TranscriptSegment(
                    start_seconds=float(start),
                    end_seconds=float(start + duration),
                    text=text,
                )
            )
        if not segments:
            raise TunelioTranscriptNotFoundError(
                "YouTube 영상에 사용할 수 있는 자막이 없습니다."
            )
        return TranscriptResult(
            provider="tunelio",
            language=payload.get("language")
            if isinstance(payload.get("language"), str)
            else None,
            is_generated=bool(payload.get("is_generated", False)),
            source_start_seconds=0,
            source_end_seconds=max(segment.end_seconds for segment in segments),
            segments=segments,
            full_text=" ".join(segment.text for segment in segments),
        )


class TunelioAudioAcquirer:
    def __init__(self, client: TunelioClient, *, timeout_seconds: float = 60) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds

    def acquire(
        self,
        source_url: str,
        *,
        start_seconds: float,
        end_seconds: float,
        destination: Path,
    ) -> None:
        reference = self._client.create_range(
            source_url,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            quality="480p",
        )
        request = Request(reference.url, headers={"User-Agent": "ShortsFlow/0.1"})
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_MEDIA_BYTES:
                    raise TranscriptProcessingError(
                        "선택 구간 영상이 처리 가능한 크기를 초과했습니다."
                    )
                written = 0
                with destination.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        written += len(chunk)
                        if written > MAX_MEDIA_BYTES:
                            raise TranscriptProcessingError(
                                "선택 구간 영상이 처리 가능한 크기를 초과했습니다."
                            )
                        output.write(chunk)
        except TranscriptProcessingError:
            raise
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            raise TranscriptProcessingError(
                "선택 구간 영상을 내려받지 못했습니다. 잠시 후 다시 시도해 주세요."
            ) from exc


class FfmpegAudioExtractor:
    def extract(self, media_path: Path, audio_path: Path) -> None:
        executable = shutil.which("ffmpeg")
        if executable is None:
            raise TranscriptProcessingError("FFmpeg 실행 파일을 찾을 수 없습니다.")
        command = [
            executable,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(media_path),
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

    def transcribe(self, audio_path: Path) -> TranscriptResult:
        try:
            with audio_path.open("rb") as audio:
                response = self._client.audio.transcriptions.create(
                    file=audio,
                    model=self._model,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
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
    ) -> TranscriptResult:
        try:
            captions = self._caption_provider.fetch(source_url)
            return self._select_range(
                captions,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                relative=False,
            )
        except (TunelioTranscriptNotFoundError, TranscriptUnavailableError):
            if (
                self._audio_acquirer is None
                or self._audio_extractor is None
                or self._stt_provider is None
            ):
                raise TranscriptProcessingError(
                    "YouTube 자막이 없으며 OpenAI STT가 설정되지 않았습니다."
                )
            with tempfile.TemporaryDirectory(prefix="shortsflow-transcript-") as temp:
                temp_path = Path(temp)
                media_path = temp_path / "source.mp4"
                audio_path = temp_path / "audio.mp3"
                self._audio_acquirer.acquire(
                    source_url,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    destination=media_path,
                )
                self._audio_extractor.extract(media_path, audio_path)
                transcript = self._stt_provider.transcribe(audio_path)
            return self._select_range(
                transcript,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                relative=True,
            )
