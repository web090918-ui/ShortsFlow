from io import BytesIO

import pytest

from app.acquisition_probe import AcquisitionProbeError, _probe_stream, run_probe
from app.youtube import PreparedVideoSource


class FakeResponse:
    def __init__(self, status: int = 206, content: bytes = b"media-bytes") -> None:
        self.status = status
        self.headers = {"Content-Type": "video/mp4"}
        self._body = BytesIO(content)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return "https://media.example/current"

    def read(self, size: int) -> bytes:
        return self._body.read(size)


def test_probe_stream_reads_only_a_small_range() -> None:
    captured_request = None

    def opener(request, timeout):
        nonlocal captured_request
        captured_request = request
        assert timeout == 5
        return FakeResponse()

    result = _probe_stream(
        {
            "url": "https://media.example/video",
            "format_id": "137",
            "http_headers": {"User-Agent": "ShortsFlow"},
        },
        timeout_seconds=5,
        opener=opener,
    )

    assert result == {
        "format_id": "137",
        "status_code": 206,
        "content_type": "video/mp4",
        "sample_bytes": 11,
        "manifest_hops": 0,
    }
    assert captured_request.get_header("Range") == "bytes=0-65535"
    assert captured_request.get_header("User-agent") == "ShortsFlow"


def test_probe_stream_rejects_an_empty_response() -> None:
    with pytest.raises(AcquisitionProbeError, match="returned no data"):
        _probe_stream(
            {"url": "https://media.example/audio", "format_id": "140"},
            timeout_seconds=5,
            opener=lambda request, timeout: FakeResponse(content=b""),
        )


def test_probe_stream_follows_hls_manifest_to_media_bytes() -> None:
    responses = iter(
        [
            FakeResponse(
                content=b"#EXTM3U\n#EXT-X-TARGETDURATION:5\nsegment.ts\n"
            ),
            FakeResponse(content=b"actual-video-bytes"),
        ]
    )
    first = next(responses)
    first.headers["Content-Type"] = "application/vnd.apple.mpegurl"

    result = _probe_stream(
        {"url": "https://media.example/playlist.m3u8", "format_id": "614"},
        timeout_seconds=5,
        opener=lambda request, timeout: first
        if request.full_url.endswith("playlist.m3u8")
        else next(responses),
    )

    assert result["manifest_hops"] == 1
    assert result["sample_bytes"] == 18


class FakeProvider:
    def prepare(self, url: str) -> PreparedVideoSource:
        assert url == "https://youtube.com/watch?v=video123"
        return PreparedVideoSource(
            metadata={
                "youtube": {
                    "video_id": "video123",
                    "title": "Test video",
                    "duration_seconds": 120,
                }
            },
            processing_reference={
                "streams": {
                    "video": {
                        "url": "https://media.example/video",
                        "format_id": "137",
                    },
                    "audio": {
                        "url": "https://media.example/audio",
                        "format_id": "140",
                    },
                }
            },
        )


def test_run_probe_returns_a_safe_report_without_stream_urls() -> None:
    report = run_probe(
        "https://youtube.com/watch?v=video123",
        provider=FakeProvider(),
        opener=lambda request, timeout: FakeResponse(),
    )

    assert report["ok"] is True
    assert report["video_id"] == "video123"
    assert report["streams"]["video"]["sample_bytes"] == 11
    assert "media.example" not in str(report)
