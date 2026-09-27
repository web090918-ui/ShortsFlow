from pathlib import Path

import pytest

from app.transcripts import (
    OpenAIWhisperProvider,
    TranscriptProcessingError,
    TranscriptProcessor,
    TranscriptResult,
    TranscriptSegment,
)
from app.tunelio import TunelioTranscriptNotFoundError
from app.youtube import VideoSourceProviderError


def _transcript(
    provider="tunelio",
    *,
    start=0.0,
    end=10.0,
    text="hello",
) -> TranscriptResult:
    return TranscriptResult(
        provider=provider,
        language="ko",
        is_generated=True,
        source_start_seconds=start,
        source_end_seconds=end,
        segments=[
            TranscriptSegment(
                start_seconds=start,
                end_seconds=end,
                text=text,
            )
        ],
        full_text=text,
    )


class CaptionStub:
    def __init__(self, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def fetch(self, source_url: str, *, language=None) -> TranscriptResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class AudioAcquirerStub:
    def __init__(self) -> None:
        self.calls = []

    def acquire(
        self,
        source_url: str,
        *,
        start_seconds: float,
        end_seconds: float,
        destination: Path,
    ) -> None:
        self.calls.append((source_url, start_seconds, end_seconds))
        destination.write_bytes(b"video")


class AudioExtractorStub:
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, media_path: Path, audio_path: Path) -> None:
        self.calls += 1
        assert media_path.read_bytes() == b"video"
        audio_path.write_bytes(b"audio")


class SttStub:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, audio_path: Path, *, language=None) -> TranscriptResult:
        self.calls += 1
        assert audio_path.read_bytes() == b"audio"
        return _transcript("openai_whisper", start=0, end=4, text="fallback")


def test_uses_tunelio_captions_without_media_or_stt() -> None:
    captions = CaptionStub(
        TranscriptResult(
            provider="tunelio",
            language="ko",
            is_generated=True,
            source_start_seconds=0,
            source_end_seconds=200,
            segments=[
                TranscriptSegment(start_seconds=50, end_seconds=59, text="before"),
                TranscriptSegment(start_seconds=60, end_seconds=70, text="selected"),
                TranscriptSegment(start_seconds=180, end_seconds=190, text="after"),
            ],
            full_text="before selected after",
        )
    )
    acquirer = AudioAcquirerStub()
    extractor = AudioExtractorStub()
    stt = SttStub()
    processor = TranscriptProcessor(
        captions,
        audio_acquirer=acquirer,
        audio_extractor=extractor,
        stt_provider=stt,
    )

    result = processor.process(
        "https://www.youtube.com/watch?v=source123",
        start_seconds=60,
        end_seconds=180,
    )

    assert result.provider == "tunelio"
    assert result.full_text == "selected"
    assert result.segments[0].start_seconds == 60
    assert acquirer.calls == []
    assert extractor.calls == 0
    assert stt.calls == 0


def test_falls_back_to_audio_and_whisper_only_when_captions_are_missing() -> None:
    captions = CaptionStub(error=TunelioTranscriptNotFoundError("missing"))
    acquirer = AudioAcquirerStub()
    extractor = AudioExtractorStub()
    stt = SttStub()
    processor = TranscriptProcessor(
        captions,
        audio_acquirer=acquirer,
        audio_extractor=extractor,
        stt_provider=stt,
    )

    result = processor.process(
        "https://www.youtube.com/watch?v=source123",
        start_seconds=60,
        end_seconds=180,
    )

    assert result.provider == "openai_whisper"
    assert result.segments[0].start_seconds == 60
    assert result.segments[0].end_seconds == 64
    assert acquirer.calls == [
        ("https://www.youtube.com/watch?v=source123", 60, 180)
    ]
    assert extractor.calls == 1
    assert stt.calls == 1


def test_falls_back_when_selected_range_has_no_captions() -> None:
    captions = CaptionStub(_transcript(start=0, end=10, text="outside range"))
    acquirer = AudioAcquirerStub()
    extractor = AudioExtractorStub()
    stt = SttStub()
    processor = TranscriptProcessor(
        captions,
        audio_acquirer=acquirer,
        audio_extractor=extractor,
        stt_provider=stt,
    )

    result = processor.process(
        "https://www.youtube.com/watch?v=source123",
        start_seconds=60,
        end_seconds=180,
    )

    assert result.provider == "openai_whisper"
    assert stt.calls == 1


def test_missing_captions_reports_unconfigured_whisper() -> None:
    processor = TranscriptProcessor(
        CaptionStub(error=TunelioTranscriptNotFoundError("missing"))
    )

    with pytest.raises(TranscriptProcessingError, match="OpenAI STT"):
        processor.process(
            "https://www.youtube.com/watch?v=source123",
            start_seconds=0,
            end_seconds=60,
        )


def test_provider_failure_does_not_spend_whisper_fallback() -> None:
    acquirer = AudioAcquirerStub()
    stt = SttStub()
    processor = TranscriptProcessor(
        CaptionStub(error=VideoSourceProviderError("credits unavailable")),
        audio_acquirer=acquirer,
        audio_extractor=AudioExtractorStub(),
        stt_provider=stt,
    )

    with pytest.raises(VideoSourceProviderError, match="credits unavailable"):
        processor.process(
            "https://www.youtube.com/watch?v=source123",
            start_seconds=0,
            end_seconds=60,
        )

    assert acquirer.calls == []
    assert stt.calls == 0


class FakeTranscriptionResponse:
    def model_dump(self):
        return {
            "language": "korean",
            "segments": [
                {"start": 0.25, "end": 2.5, "text": " 안녕하세요 "},
            ],
        }


class FakeTranscriptions:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return FakeTranscriptionResponse()


class FakeOpenAI:
    def __init__(self) -> None:
        self.audio = type("Audio", (), {"transcriptions": FakeTranscriptions()})()


def test_openai_whisper_requests_segment_timestamps(tmp_path) -> None:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")
    client = FakeOpenAI()

    result = OpenAIWhisperProvider(client).transcribe(audio_path, language="ko-KR")

    assert result.provider == "openai_whisper"
    assert result.segments[0].start_seconds == 0.25
    assert client.audio.transcriptions.kwargs["model"] == "whisper-1"
    assert client.audio.transcriptions.kwargs["response_format"] == "verbose_json"
    assert client.audio.transcriptions.kwargs["timestamp_granularities"] == [
        "segment"
    ]
    assert client.audio.transcriptions.kwargs["language"] == "ko"
