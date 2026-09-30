from datetime import timedelta
from pathlib import Path

import pytest

from app import acquisition
from app.acquisition import (
    AcquisitionError,
    AcquisitionPendingError,
    ApifyTitanClient,
    CachedTitanAcquirer,
    youtube_video_id,
)
from app.source_media import (
    InMemorySourceMediaRepository,
    SourceMediaEntry,
    SourceMediaStatus,
    utcnow,
)


URL = "https://www.youtube.com/watch?v=longvideo1"


class FakeApify:
    """Scripted Titan API: statuses are consumed one per get_run call."""

    def __init__(self, *, statuses, items=None) -> None:
        self.statuses = list(statuses)
        self.items = items or [
            {
                "id": "longvideo1",
                "title": "Long",
                "durationSec": 1663,
                "status": "completed",
                "downloadedFileUrl": "https://files.example.com/long.mp4",
            }
        ]
        self.requests = []

    def __call__(self, method, path, *, params=None, body=None):
        self.requests.append((method, path, body))
        if method == "POST" and path.endswith("/abort"):
            return {"data": {"status": "ABORTING"}}
        if method == "POST" and path.endswith("/runs"):
            return {"data": {"id": "run-long", "defaultDatasetId": "ds-long", "status": "READY"}}
        if path.startswith("/v2/actor-runs/"):
            status = self.statuses.pop(0) if self.statuses else "RUNNING"
            return {"data": {"id": "run-long", "status": status, "defaultDatasetId": "ds-long"}}
        if path.startswith("/v2/datasets/"):
            return self.items
        raise AssertionError(f"unexpected {method} {path}")


@pytest.fixture
def fast_clock(monkeypatch):
    monkeypatch.setattr(acquisition.time, "sleep", lambda seconds: None)
    # monotonic advances 10s per call so wait budgets expire quickly in tests.
    counter = {"t": 0.0}

    def monotonic():
        counter["t"] += 10.0
        return counter["t"]

    monkeypatch.setattr(acquisition.time, "monotonic", monotonic)
    downloads: list[str] = []

    def fake_download(url, destination, **kwargs):
        downloads.append(url)
        destination.write_bytes(b"video")
        return 5

    monkeypatch.setattr(acquisition, "download_to_file", fake_download)
    return downloads


def _acquirer(fake: FakeApify, cache, **overrides) -> CachedTitanAcquirer:
    client = ApifyTitanClient("token", poll_interval_seconds=0)
    client._request = fake  # type: ignore[method-assign]
    options = {"initial_wait_seconds": 15, "retry_after_seconds": 60, "quality": "720"}
    options.update(overrides)
    return CachedTitanAcquirer(client, cache, **options)


def test_youtube_video_id_handles_common_url_shapes() -> None:
    assert youtube_video_id("https://www.youtube.com/watch?v=abc123&t=5") == "abc123"
    assert youtube_video_id("https://youtu.be/abc123") == "abc123"
    assert youtube_video_id("https://www.youtube.com/shorts/abc123") == "abc123"
    assert youtube_video_id("https://example.com/video") == "https://example.com/video"


def test_short_run_completes_inline_and_caches_the_link(fast_clock, tmp_path: Path) -> None:
    cache = InMemorySourceMediaRepository()
    acquirer = _acquirer(FakeApify(statuses=["RUNNING", "SUCCEEDED"]), cache)

    acquired = acquirer.acquire(URL, destination=tmp_path / "in.mp4")

    assert acquired.provider == "apify_titan"
    assert acquired.title == "Long"
    assert fast_clock == ["https://files.example.com/long.mp4"]
    entry = cache.get("apify_titan:longvideo1:720")
    assert entry is not None
    assert entry.status == SourceMediaStatus.READY
    assert entry.file_url == "https://files.example.com/long.mp4"
    assert entry.expires_at is not None and entry.expires_at > utcnow()


def test_long_run_defers_then_resumes_from_the_pending_entry(fast_clock, tmp_path: Path) -> None:
    cache = InMemorySourceMediaRepository()
    first = FakeApify(statuses=["RUNNING"] * 10)
    acquirer = _acquirer(first, cache)

    with pytest.raises(AcquisitionPendingError) as excinfo:
        acquirer.acquire(URL, destination=tmp_path / "in.mp4")

    assert excinfo.value.retry_after_seconds == 60
    assert fast_clock == []
    pending = cache.get("apify_titan:longvideo1:720")
    assert pending is not None and pending.status == SourceMediaStatus.PENDING
    assert pending.run_id == "run-long"
    # The run was started exactly once and never aborted.
    assert [r[1] for r in first.requests if r[0] == "POST"] == [
        "/v2/acts/titan_network~titan-youtube-video-downloader/runs"
    ]

    # A later Worker attempt finds the pending run finished and downloads the file.
    second = FakeApify(statuses=["SUCCEEDED"])
    resumed = _acquirer(second, cache)
    acquired = resumed.acquire(URL, destination=tmp_path / "again.mp4")

    assert acquired.duration_seconds == 1663
    assert fast_clock == ["https://files.example.com/long.mp4"]
    assert not any(r[1].endswith("/runs") for r in second.requests)
    assert cache.get("apify_titan:longvideo1:720").status == SourceMediaStatus.READY


def test_ready_cache_skips_the_provider_entirely(fast_clock, tmp_path: Path) -> None:
    cache = InMemorySourceMediaRepository()
    now = utcnow()
    cache.save(
        SourceMediaEntry(
            key="apify_titan:longvideo1:720",
            video_id="longvideo1",
            quality="720",
            status=SourceMediaStatus.READY,
            provider="apify_titan",
            file_url="https://files.example.com/cached.mp4",
            title="Cached",
            duration_seconds=1663,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(hours=1),
        )
    )
    fake = FakeApify(statuses=[])

    acquired = _acquirer(fake, cache).acquire(URL, destination=tmp_path / "in.mp4")

    assert acquired.title == "Cached"
    assert fast_clock == ["https://files.example.com/cached.mp4"]
    assert fake.requests == []


def test_expired_cache_starts_a_new_run(fast_clock, tmp_path: Path) -> None:
    cache = InMemorySourceMediaRepository()
    now = utcnow()
    cache.save(
        SourceMediaEntry(
            key="apify_titan:longvideo1:720",
            video_id="longvideo1",
            quality="720",
            status=SourceMediaStatus.READY,
            provider="apify_titan",
            file_url="https://files.example.com/stale.mp4",
            created_at=now - timedelta(days=2),
            updated_at=now - timedelta(days=2),
            expires_at=now - timedelta(hours=1),
        )
    )
    fake = FakeApify(statuses=["SUCCEEDED"])

    _acquirer(fake, cache).acquire(URL, destination=tmp_path / "in.mp4")

    assert any(r[1].endswith("/runs") for r in fake.requests)
    assert fast_clock == ["https://files.example.com/long.mp4"]


def test_pending_past_its_limit_is_aborted_and_fails_without_retry(fast_clock, tmp_path):
    cache = InMemorySourceMediaRepository()
    now = utcnow()
    cache.save(
        SourceMediaEntry(
            key="apify_titan:longvideo1:720",
            video_id="longvideo1",
            quality="720",
            status=SourceMediaStatus.PENDING,
            provider="apify_titan",
            run_id="run-long",
            dataset_id="ds-long",
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(minutes=1),
            expires_at=now - timedelta(minutes=1),
        )
    )
    fake = FakeApify(statuses=["RUNNING"] * 5)

    with pytest.raises(AcquisitionError) as excinfo:
        _acquirer(fake, cache).acquire(URL, destination=tmp_path / "in.mp4")

    assert excinfo.value.retryable is False
    assert ("POST", "/v2/actor-runs/run-long/abort", None) in fake.requests
    assert cache.get("apify_titan:longvideo1:720").status == SourceMediaStatus.FAILED


def test_failed_run_marks_cache_failed_and_is_retryable(fast_clock, tmp_path: Path) -> None:
    cache = InMemorySourceMediaRepository()

    with pytest.raises(AcquisitionError) as excinfo:
        _acquirer(FakeApify(statuses=["FAILED"]), cache).acquire(
            URL, destination=tmp_path / "in.mp4"
        )

    assert excinfo.value.retryable is True
    assert cache.get("apify_titan:longvideo1:720").status == SourceMediaStatus.FAILED
