from pathlib import Path

import pytest

from app import acquisition
from app.acquisition import AcquisitionError, ApifyTitanProvider


class FakeApify:
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


@pytest.fixture
def provider(monkeypatch) -> ApifyTitanProvider:
    monkeypatch.setattr(acquisition.time, "sleep", lambda seconds: None)
    return ApifyTitanProvider("token", poll_interval_seconds=0, run_timeout_seconds=30)


def test_titan_provider_runs_actor_and_downloads_file(monkeypatch, provider, tmp_path: Path):
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
    monkeypatch.setattr(provider, "_request", fake)
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
    assert progress and progress[0] <= progress[-1]


def test_titan_provider_reports_failed_item_without_retry(monkeypatch, provider, tmp_path):
    fake = FakeApify(items=[{"id": "abc", "status": "failed"}], run_statuses=("SUCCEEDED",))
    monkeypatch.setattr(provider, "_request", fake)

    with pytest.raises(AcquisitionError) as excinfo:
        provider.acquire("https://youtu.be/abc", destination=tmp_path / "input.mp4")

    assert excinfo.value.retryable is False


def test_titan_provider_reports_actor_failure_as_retryable(monkeypatch, provider, tmp_path):
    fake = FakeApify(items=[], run_statuses=("FAILED",))
    monkeypatch.setattr(provider, "_request", fake)

    with pytest.raises(AcquisitionError) as excinfo:
        provider.acquire("https://youtu.be/abc", destination=tmp_path / "input.mp4")

    assert excinfo.value.retryable is True


def test_titan_provider_rejects_insecure_download_url(monkeypatch, provider, tmp_path):
    fake = FakeApify(
        items=[{"status": "completed", "downloadedFileUrl": "http://insecure/abc.mp4"}],
        run_statuses=("SUCCEEDED",),
    )
    monkeypatch.setattr(provider, "_request", fake)

    with pytest.raises(AcquisitionError) as excinfo:
        provider.acquire("https://youtu.be/abc", destination=tmp_path / "input.mp4")

    assert excinfo.value.retryable is False


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
