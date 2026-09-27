import json

import app.tunelio as tunelio_module
from app.tunelio import TunelioClient


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_prepare_maps_tunelio_metadata_without_exposing_key(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        assert request.get_header("Authorization") == "Bearer server-secret"
        assert timeout == 30
        assert request.full_url.startswith("https://tunelio.dev/info?")
        return FakeResponse(
            {
                "title": "Test video",
                "duration_seconds": 968,
                "thumbnail": "https://i.ytimg.com/test.jpg",
                "formats": [{"quality": "480p", "width": 854, "height": 480}],
            }
        )

    monkeypatch.setattr(tunelio_module, "urlopen", fake_urlopen)

    prepared = TunelioClient("server-secret").prepare(
        "https://www.youtube.com/watch?v=video123"
    )

    assert prepared.metadata["youtube"]["title"] == "Test video"
    assert prepared.metadata["youtube"]["duration_seconds"] == 968
    assert prepared.metadata["media"]["provider"] == "tunelio"
    assert prepared.processing_reference == {
        "provider": "tunelio",
        "webpage_url": "https://www.youtube.com/watch?v=video123",
    }


def test_create_range_appends_start_and_end_to_signed_url(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        assert request.full_url.startswith("https://tunelio.dev/create?")
        assert "quality=480p" in request.full_url
        return FakeResponse(
            {
                "url": "https://tunelio.dev/tunnel?exp=123&sig=signed-value",
                "filename": "video.mp4",
                "expires": 123,
            }
        )

    monkeypatch.setattr(tunelio_module, "urlopen", fake_urlopen)

    reference = TunelioClient("server-secret").create_range(
        "https://www.youtube.com/watch?v=video123",
        start_seconds=60,
        end_seconds=120,
    )

    assert reference.url == (
        "https://tunelio.dev/tunnel?exp=123&sig=signed-value&start=60&end=120"
    )
    assert reference.expires_at == 123
