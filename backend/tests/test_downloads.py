from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.downloads as downloads_module
import app.sources as sources_module
from app.main import app
from app.acquisition import AcquiredVideo, AcquisitionError
from app.downloads import ProviderRangeDownloader
from app.youtube import PreparedVideoSource, VideoSourceProviderError


client = TestClient(app)


class StubYouTubeProvider:
    def prepare(self, url: str) -> PreparedVideoSource:
        return PreparedVideoSource(
            metadata={
                "youtube": {
                    "video_id": "range123",
                    "title": "Range video",
                    "duration_seconds": 600,
                },
                "media": {"video": {"format_id": "137"}, "audio": {"format_id": "140"}},
            },
            processing_reference={"provider": "youtube"},
        )


class StubRangeDownloader:
    def download(
        self,
        url: str,
        *,
        start_seconds: float,
        end_seconds: float,
        output_directory: Path,
        progress=None,
    ) -> Path:
        assert url == "https://www.youtube.com/watch?v=range123"
        assert start_seconds == 60
        assert end_seconds == 180
        output_directory.mkdir(parents=True, exist_ok=True)
        if progress is not None:
            progress(50)
        artifact = output_directory / "selected-range.mp4"
        artifact.write_bytes(b"selected-video-bytes")
        if progress is not None:
            progress(100)
        return artifact


def _create_ready_source(monkeypatch) -> dict:
    monkeypatch.setattr(sources_module, "youtube_provider", StubYouTubeProvider())
    response = client.post(
        "/sources?prepare=true",
        json={"url": "https://www.youtube.com/watch?v=range123"},
    )
    assert response.status_code == 201
    return response.json()


def test_creates_range_download_job_and_serves_mp4(monkeypatch) -> None:
    source = _create_ready_source(monkeypatch)
    monkeypatch.setattr(downloads_module, "range_downloader", StubRangeDownloader())

    create_response = client.post(
        f"/sources/{source['id']}/downloads",
        json={
            "start_seconds": 60,
            "end_seconds": 180,
            "rights_confirmed": True,
            "template_id": "BOLD_HIGHLIGHT",
        },
    )

    assert create_response.status_code == 202
    created_job = create_response.json()
    assert created_job["status"] == "QUEUED"
    assert created_job["duration_seconds"] == 120
    assert created_job["template_id"] == "BOLD_HIGHLIGHT"
    assert created_job["download_url"] is None

    status_response = client.get(f"/downloads/{created_job['id']}")
    assert status_response.status_code == 200
    ready_job = status_response.json()
    assert ready_job["status"] == "READY"
    assert ready_job["progress"] == 100
    assert ready_job["download_url"] == f"/downloads/{created_job['id']}/file"

    file_response = client.get(ready_job["download_url"])
    assert file_response.status_code == 200
    assert file_response.content == b"selected-video-bytes"
    assert file_response.headers["content-type"] == "video/mp4"
    assert "shortsflow-60-180.mp4" in file_response.headers["content-disposition"]


def test_rejects_range_past_source_duration(monkeypatch) -> None:
    source = _create_ready_source(monkeypatch)

    response = client.post(
        f"/sources/{source['id']}/downloads",
        json={"start_seconds": 590, "end_seconds": 610, "rights_confirmed": True},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "선택한 종료 시간이 원본 영상 길이를 초과합니다."


def test_rejects_range_longer_than_sixty_minutes(monkeypatch) -> None:
    source = _create_ready_source(monkeypatch)

    response = client.post(
        f"/sources/{source['id']}/downloads",
        json={"start_seconds": 0, "end_seconds": 3601, "rights_confirmed": True},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "한 번에 최대 60분까지 선택할 수 있습니다."


def test_requires_source_rights_confirmation(monkeypatch) -> None:
    source = _create_ready_source(monkeypatch)

    response = client.post(
        f"/sources/{source['id']}/downloads",
        json={"start_seconds": 0, "end_seconds": 60, "rights_confirmed": False},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "원본 영상에 대한 소유권 또는 필요한 이용 허가를 확인해야 합니다."
    )


def test_rejects_unknown_template(monkeypatch) -> None:
    source = _create_ready_source(monkeypatch)

    response = client.post(
        f"/sources/{source['id']}/downloads",
        json={
            "start_seconds": 0,
            "end_seconds": 60,
            "rights_confirmed": True,
            "template_id": "UNKNOWN",
        },
    )

    assert response.status_code == 422


def test_unknown_source_returns_404_even_with_source_url() -> None:
    response = client.post(
        "/sources/00000000-0000-0000-0000-000000000001/downloads",
        json={
            "source_url": "https://www.youtube.com/watch?v=range123",
            "start_seconds": 60,
            "end_seconds": 120,
            "rights_confirmed": True,
        },
    )

    assert response.status_code == 404


class StubProvider:
    name = "stub"

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    def acquire(self, url, *, destination, progress=None):
        if self.error is not None:
            raise self.error
        destination.write_bytes(b"full-video")
        if progress is not None:
            progress(100)
        return AcquiredVideo(path=destination, provider=self.name)


class StubProcessor:
    def __init__(self) -> None:
        self.calls = []

    def probe(self, media_path):
        raise AssertionError("not used")

    def trim(self, input_path, output_path, *, start_seconds, end_seconds, max_height=None):
        self.calls.append((start_seconds, end_seconds, max_height))
        assert input_path.read_bytes() == b"full-video"
        output_path.write_bytes(b"proxy")

    def convert_to_vertical(self, input_path, output_path):
        raise AssertionError("not used")

    def trim_to_vertical(self, input_path, output_path, *, start_seconds, end_seconds):
        raise AssertionError("not used")


def test_provider_range_downloader_cuts_480p_proxy_and_removes_source(tmp_path: Path):
    processor = StubProcessor()
    downloader = ProviderRangeDownloader(StubProvider(), processor)
    progress: list[int] = []

    artifact = downloader.download(
        "https://www.youtube.com/watch?v=range123",
        start_seconds=60,
        end_seconds=180,
        output_directory=tmp_path / "job",
        progress=progress.append,
    )

    assert artifact == tmp_path / "job" / "selected-range.mp4"
    assert artifact.read_bytes() == b"proxy"
    assert processor.calls == [(60, 180, 480)]
    assert not (tmp_path / "job" / "source.mp4").exists()
    assert progress[-1] == 100
    assert max(progress[:-1]) <= 80


def test_provider_range_downloader_reports_acquisition_failure(tmp_path: Path):
    downloader = ProviderRangeDownloader(
        StubProvider(error=AcquisitionError("blocked")), StubProcessor()
    )

    with pytest.raises(VideoSourceProviderError, match="blocked"):
        downloader.download(
            "https://www.youtube.com/watch?v=range123",
            start_seconds=0,
            end_seconds=10,
            output_directory=tmp_path / "job",
        )
