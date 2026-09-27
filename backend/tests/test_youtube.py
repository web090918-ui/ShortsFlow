import app.youtube as youtube_module
from app.youtube import VideoSourceProviderError, YouTubeSourceProvider
from yt_dlp.utils import DownloadError


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
                {
                    "format_id": "combined",
                    "url": "https://media.example/combined",
                    "ext": "mp4",
                    "acodec": "mp4a",
                    "vcodec": "avc1",
                    "height": 360,
                },
            ],
        }


def test_provider_separates_public_metadata_from_private_stream_urls(monkeypatch) -> None:
    monkeypatch.setattr(youtube_module.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(youtube_module, "_deno_runtime_path", lambda: "/runtime/deno")

    prepared = YouTubeSourceProvider().prepare("https://youtube.com/watch?v=video123")

    assert prepared.metadata["youtube"]["title"] == "A video"
    assert prepared.metadata["media"]["audio"]["format_id"] == "audio"
    assert prepared.metadata["media"]["video"]["format_id"] == "video"
    assert "url" not in prepared.metadata["media"]["audio"]
    assert prepared.processing_reference["streams"]["audio"]["url"] == (
        "https://media.example/audio"
    )


class BotChallengeYoutubeDL(FakeYoutubeDL):
    def extract_info(self, url, download):
        raise DownloadError("Sign in to confirm you’re not a bot")


def test_provider_reports_cloud_ip_bot_challenge(monkeypatch) -> None:
    monkeypatch.setattr(youtube_module.yt_dlp, "YoutubeDL", BotChallengeYoutubeDL)
    monkeypatch.setattr(youtube_module, "_deno_runtime_path", lambda: "/runtime/deno")

    try:
        YouTubeSourceProvider().prepare("https://youtube.com/watch?v=video123")
    except VideoSourceProviderError as exc:
        assert str(exc) == (
            "YouTube가 현재 서버 요청을 제한했습니다. 잠시 후 다시 시도해 주세요."
        )
    else:
        raise AssertionError("Expected the bot challenge to become a provider error")
