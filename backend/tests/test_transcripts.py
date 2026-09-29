import json
from pathlib import Path

import pytest

from app.acquisition import AcquisitionError, SubtitlesUnavailableError
from app.transcripts import (
    CaptionsUnavailableError,
    OpenAIWhisperProvider,
    ProviderAudioAcquirer,
    TitanCaptionProvider,
    TranscriptProcessingError,
    TranscriptProcessor,
    TranscriptResult,
    TranscriptSegment,
    parse_caption_text,
)


def _transcript(
    provider="apify_titan",
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

    def acquire(self, source_url: str, *, destination: Path) -> None:
        self.calls.append(source_url)
        destination.write_bytes(b"video")


class AudioExtractorStub:
    def __init__(self) -> None:
        self.calls = []

    def extract(
        self, media_path: Path, audio_path: Path, *, start_seconds=None, end_seconds=None
    ) -> None:
        self.calls.append((start_seconds, end_seconds))
        assert media_path.read_bytes() == b"video"
        audio_path.write_bytes(b"audio")


class SttStub:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, audio_path: Path, *, language=None) -> TranscriptResult:
        self.calls += 1
        assert audio_path.read_bytes() == b"audio"
        return _transcript("openai_whisper", start=0, end=4, text="fallback")


def test_uses_captions_without_media_or_stt() -> None:
    captions = CaptionStub(
        TranscriptResult(
            provider="apify_titan",
            language="ko",
            is_generated=False,
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

    assert result.provider == "apify_titan"
    assert result.full_text == "selected"
    assert result.segments[0].start_seconds == 60
    assert acquirer.calls == []
    assert extractor.calls == []
    assert stt.calls == 0


def test_falls_back_to_full_source_audio_and_whisper_when_captions_are_missing() -> None:
    captions = CaptionStub(error=CaptionsUnavailableError("missing"))
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
    assert acquirer.calls == ["https://www.youtube.com/watch?v=source123"]
    # The extractor, not the acquirer, applies the selected range.
    assert extractor.calls == [(60, 180)]
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
    processor = TranscriptProcessor(CaptionStub(error=CaptionsUnavailableError("missing")))

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
        CaptionStub(error=AcquisitionError("quota exhausted", retryable=False)),
        audio_acquirer=acquirer,
        audio_extractor=AudioExtractorStub(),
        stt_provider=stt,
    )

    with pytest.raises(AcquisitionError, match="quota exhausted"):
        processor.process(
            "https://www.youtube.com/watch?v=source123",
            start_seconds=0,
            end_seconds=60,
        )

    assert acquirer.calls == []
    assert stt.calls == 0


class TitanStub:
    def __init__(self, text=None, error=None) -> None:
        self.text = text
        self.error = error
        self.requests = []

    def fetch_subtitles(self, url: str, *, language: str) -> str:
        self.requests.append((url, language))
        if self.error is not None:
            raise self.error
        return self.text

    def acquire(self, url, *, destination, progress=None):
        destination.write_bytes(b"video")


def test_titan_caption_provider_parses_json3_and_strips_region() -> None:
    payload = {
        "events": [
            {"tStartMs": 1000, "dDurationMs": 2000, "segs": [{"utf8": "안녕 "}, {"utf8": "하세요"}]},
            {"tStartMs": 4000, "dDurationMs": 1000, "segs": [{"utf8": "\n"}]},
            {"tStartMs": 6000, "dDurationMs": 1500, "segs": [{"utf8": "둘째 줄"}]},
        ]
    }
    titan = TitanStub(text=json.dumps(payload))

    result = TitanCaptionProvider(titan).fetch(
        "https://youtu.be/abc", language="ko-KR"
    )

    assert titan.requests == [("https://youtu.be/abc", "ko")]
    assert result.provider == "apify_titan"
    assert result.language == "ko"
    assert [segment.text for segment in result.segments] == ["안녕 하세요", "둘째 줄"]
    assert result.segments[0].start_seconds == 1.0
    assert result.segments[0].end_seconds == 3.0
    assert result.source_end_seconds == 7.5


def test_titan_caption_provider_maps_missing_track_to_captions_unavailable() -> None:
    titan = TitanStub(error=SubtitlesUnavailableError())

    with pytest.raises(CaptionsUnavailableError):
        TitanCaptionProvider(titan).fetch("https://youtu.be/abc", language="ko")

    with pytest.raises(CaptionsUnavailableError):
        TitanCaptionProvider(TitanStub(text="WEBVTT\n\n")).fetch(
            "https://youtu.be/abc", language="ko"
        )


def test_parse_caption_text_handles_vtt_and_srt() -> None:
    vtt = (
        "WEBVTT\nKind: captions\n\n"
        "00:00:01.000 --> 00:00:02.500 align:start\n<c>첫</c> 문장\n\n"
        "00:01:10.250 --> 00:01:12.000\n둘째\n문장\n"
    )
    srt = "1\n00:00:01,000 --> 00:00:02,500\n첫 문장\n\n2\n01:00:00,000 --> 01:00:01,000\n한 시간 뒤\n"

    vtt_segments = parse_caption_text(vtt)
    srt_segments = parse_caption_text(srt)

    assert [(s.start_seconds, s.end_seconds, s.text) for s in vtt_segments] == [
        (1.0, 2.5, "첫 문장"),
        (70.25, 72.0, "둘째 문장"),
    ]
    assert srt_segments[1].start_seconds == 3600.0
    assert srt_segments[1].text == "한 시간 뒤"


def test_provider_audio_acquirer_wraps_acquisition_errors(tmp_path: Path) -> None:
    class FailingProvider:
        name = "stub"

        def acquire(self, url, *, destination, progress=None):
            raise AcquisitionError("blocked")

    with pytest.raises(TranscriptProcessingError, match="blocked"):
        ProviderAudioAcquirer(FailingProvider()).acquire(
            "https://youtu.be/abc", destination=tmp_path / "source.mp4"
        )

    ProviderAudioAcquirer(TitanStub()).acquire(
        "https://youtu.be/abc", destination=tmp_path / "ok.mp4"
    )
    assert (tmp_path / "ok.mp4").read_bytes() == b"video"


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
