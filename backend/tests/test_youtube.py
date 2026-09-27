import app.youtube as youtube_module
from app.youtube import YouTubeSourceProvider


class FakeYoutubeDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def extract_info(self, url, download):
        assert download is False
        return {
            "id": "video123",
            "title": "A video",
            "duration": 90,
            "channel_id": "channel123",
            "channel": "A channel",
            "thumbnail": "https://i.ytimg.com/example.jpg",
            "webpage_url": url,
            "formats": [
                {
                    "format_id": "audio",
                    "url": "https://media.example/audio",
                    "ext": "m4a",
                    "acodec": "mp4a",
                    "vcodec": "none",
                    "abr": 128,
                },
                {
                    "format_id": "video",
                    "url": "https://media.example/video",
                    "ext": "mp4",
                    "acodec": "none",
                    "vcodec": "avc1",
                    "height": 1080,
                },
            ],
        }


def test_provider_separates_public_metadata_from_private_stream_urls(monkeypatch) -> None:
    monkeypatch.setattr(youtube_module.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    prepared = YouTubeSourceProvider().prepare("https://youtube.com/watch?v=video123")

    assert prepared.metadata["youtube"]["title"] == "A video"
    assert prepared.metadata["media"]["audio"]["format_id"] == "audio"
    assert "url" not in prepared.metadata["media"]["audio"]
    assert prepared.processing_reference["streams"]["audio"]["url"] == (
        "https://media.example/audio"
    )
