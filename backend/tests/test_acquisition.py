import json
from pathlib import Path

import pytest

from app import acquisition
from app.acquisition import (
    AcquisitionError,
    ApifyTitanClient,
    ApifyTitanProvider,
    SubtitlesUnavailableError,
)


class FakeApify:
    """Replaces ApifyTitanClient._request with an in-memory actor."""

    def __init__(self, *, items, run_statuses=("RUNNING", "SUCCEEDED")) -> None:
        self.items = items
        self.run_statuses = list(run_statuses)
        self.requests: list[tuple[str, str, dict | None]] = []

    def __call__(self, method, path, *, params=None, body=None):
        self.requests.append((method, path, body))
        if method == "POST" and path.endswith("/runs"):
            return {"data": {"id": "run-1", "defaultDatasetId": "dataset-1", "status": "READY"}}
        if path.startswith("/v2/actor-runs/"):
            status = self.run_statuses.pop(0)
            return {"data": {"id": "run-1", "status": status, "defaultDatasetId": "dataset-1"}}
        if path.startswith("/v2/datasets/"):
            return self.items
        raise AssertionError(f"unexpected request {method} {path}")


def _provider(monkeypatch, fake: FakeApify) -> ApifyTitanProvider:
    monkeypatch.setattr(acquisition.time, "sleep", lambda seconds: None)
    client = ApifyTitanClient("token", poll_interval_seconds=0)
    monkeypatch.setattr(client, "_request", fake)
    return ApifyTitanProvider(client, run_timeout_seconds=30, metadata_timeout_seconds=30)


def test_titan_provider_runs_actor_and_downloads_file(monkeypatch, tmp_path: Path):
    fake = FakeApify(
        items=[
            {
                "id": "abc",
                "title": "Sample",
                "durationSec": 321,
                "status": "completed",
                "downloadedFileUrl": "https://files.example.com/abc.mp4",
            }
        ]
    )
    provider = _provider(monkeypatch, fake)
    downloads: list[str] = []

    def fake_download(url, destination, **kwargs):
        downloads.append(url)
        destination.write_bytes(b"video")
        return 5

    monkeypatch.setattr(acquisition, "download_to_file", fake_download)
    progress: list[int] = []

    acquired = provider.acquire(
        "https://www.youtube.com/watch?v=abc",
        destination=tmp_path / "input.mp4",
        progress=progress.append,
    )

    assert acquired.provider == "apify_titan"
    assert acquired.title == "Sample"
    assert acquired.duration_seconds == 321
    assert acquired.path.read_bytes() == b"video"
    assert downloads == ["https://files.example.com/abc.mp4"]
    start_body = fake.requests[0][2]
    assert start_body["startUrls"] == ["https://www.youtube.com/watch?v=abc"]
    assert start_body["outputType"] == "media"
    assert start_body["format"] == "mp4"
    assert start_body["quality"] == "1080"
    assert start_body["maxWaitSec"] == 30
    assert progress and progress[0] <= progress[-1]


def test_titan_provider_reports_failed_item_without_retry(monkeypatch, tmp_path):
    fake = FakeApify(items=[{"id": "abc", "status": "failed"}], run_statuses=("SUCCEEDED",))
    provider = _provider(monkeypatch, fake)

    with pytest.raises(AcquisitionError) as excinfo:
        provider.acquire("https://youtu.be/abc", destination=tmp_path / "input.mp4")

    assert excinfo.value.retryable is False


def test_titan_provider_reports_actor_failure_as_retryable(monkeypatch, tmp_path):
    provider = _provider(monkeypatch, FakeApify(items=[], run_statuses=("FAILED",)))

    with pytest.raises(AcquisitionError) as excinfo:
        provider.acquire("https://youtu.be/abc", destination=tmp_path / "input.mp4")

    assert excinfo.value.retryable is True


def test_titan_provider_rejects_insecure_download_url(monkeypatch, tmp_path):
    fake = FakeApify(
        items=[{"status": "completed", "downloadedFileUrl": "http://insecure/abc.mp4"}],
        run_statuses=("SUCCEEDED",),
    )
    provider = _provider(monkeypatch, fake)

    with pytest.raises(AcquisitionError) as excinfo:
        provider.acquire("https://youtu.be/abc", destination=tmp_path / "input.mp4")

    assert excinfo.value.retryable is False


def test_titan_provider_prepares_metadata_from_info_json(monkeypatch):
    fake = FakeApify(
        items=[
            {
                "id": "abc",
                "title": "Item title",
                "durationSec": 300,
                "status": "completed",
                "downloadedFileUrl": "https://files.example.com/abc.info.json",
            }
        ],
        run_statuses=("SUCCEEDED",),
    )
    provider = _provider(monkeypatch, fake)
    info = {
        "id": "abc",
        "title": "Info title",
        "duration": 301,
        "channel": "Channel",
        "thumbnail": "https://i.ytimg.com/abc.jpg",
        "upload_date": "20240101",
        "view_count": 42,
    }
    monkeypatch.setattr(acquisition, "download_text", lambda url, **kwargs: json.dumps(info))

    prepared = provider.prepare("https://youtu.be/abc")

    assert fake.requests[0][2]["outputType"] == "metadata"
    youtube = prepared.metadata["youtube"]
    assert youtube["title"] == "Info title"
    assert youtube["duration_seconds"] == 301
    assert youtube["channel_title"] == "Channel"
    assert youtube["thumbnail_url"] == "https://i.ytimg.com/abc.jpg"
    assert prepared.metadata["media"] == {"provider": "apify_titan"}
    assert prepared.processing_reference == {
        "provider": "apify_titan",
        "webpage_url": "https://youtu.be/abc",
    }


def test_titan_provider_prepare_falls_back_to_item_fields(monkeypatch):
    fake = FakeApify(
        items=[
            {
                "id": "abc",
                "title": "Item title",
                "durationSec": 300,
                "status": "completed",
                "downloadedFileUrl": "https://files.example.com/abc.info.json",
            }
        ],
        run_statuses=("SUCCEEDED",),
    )
    provider = _provider(monkeypatch, fake)

    def failing_download(url, **kwargs):
        raise AcquisitionError("unreachable")

    monkeypatch.setattr(acquisition, "download_text", failing_download)

    prepared = provider.prepare("https://youtu.be/abc")

    assert prepared.metadata["youtube"]["title"] == "Item title"
    assert prepared.metadata["youtube"]["duration_seconds"] == 300


def test_titan_provider_fetches_subtitles_for_language(monkeypatch):
    fake = FakeApify(
        items=[
            {
                "id": "abc",
                "status": "completed",
                "downloadFiles": [
                    {"status": "completed", "url": "https://files.example.com/abc.ko.json3"}
                ],
            }
        ],
        run_statuses=("SUCCEEDED",),
    )
    provider = _provider(monkeypatch, fake)
    fetched: list[str] = []

    def fake_text(url, **kwargs):
        fetched.append(url)
        return '{"events": []}'

    monkeypatch.setattr(acquisition, "download_text", fake_text)

    text = provider.fetch_subtitles("https://youtu.be/abc", language="ko")

    assert text == '{"events": []}'
    assert fetched == ["https://files.example.com/abc.ko.json3"]
    body = fake.requests[0][2]
    assert body["outputType"] == "subtitles"
    assert body["subtitleLanguages"] == ["ko"]
    assert body["subtitleFormat"] == "json3"


def test_titan_provider_reports_missing_subtitles(monkeypatch):
    provider = _provider(
        monkeypatch,
        FakeApify(items=[{"id": "abc", "status": "skipped"}], run_statuses=("SUCCEEDED",)),
    )

    with pytest.raises(SubtitlesUnavailableError):
        provider.fetch_subtitles("https://youtu.be/abc", language="ko")

    failed_run = _provider(monkeypatch, FakeApify(items=[], run_statuses=("FAILED",)))
    with pytest.raises(AcquisitionError) as excinfo:
        failed_run.fetch_subtitles("https://youtu.be/abc", language="ko")
    # A retryable run failure is surfaced, not mistaken for a missing track.
    assert not isinstance(excinfo.value, SubtitlesUnavailableError)


def test_download_to_file_enforces_size_limit(monkeypatch, tmp_path: Path) -> None:
    class FakeResponse:
        headers = {"Content-Length": "10"}

        def __init__(self) -> None:
            self.chunks = [b"12345", b"67890"]

        def read(self, size):
            return self.chunks.pop(0) if self.chunks else b""

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(acquisition, "urlopen", lambda request, timeout: FakeResponse())

    with pytest.raises(AcquisitionError) as excinfo:
        acquisition.download_to_file(
            "https://files.example.com/a.mp4",
            tmp_path / "a.mp4",
            max_bytes=8,
            timeout_seconds=1,
        )
    assert excinfo.value.retryable is False

    written = acquisition.download_to_file(
        "https://files.example.com/a.mp4",
        tmp_path / "b.mp4",
        max_bytes=10,
        timeout_seconds=1,
    )
    assert written == 10
    assert (tmp_path / "b.mp4").read_bytes() == b"1234567890"
