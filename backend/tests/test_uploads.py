from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.processing_jobs as jobs_module
import app.sources as sources_module
from app.acquisition import (
    AcquisitionError,
    RoutingAcquirer,
    UploadAcquirer,
    is_upload_url,
    upload_source_url,
)
from app.main import app
from app.processing_jobs import InMemoryProcessingJobRepository
from app.ranking import HeuristicRanker
from app.shorts_pipeline import LocalArtifactStorage
from app.transcripts import (
    CaptionsUnavailableError,
    TitanCaptionProvider,
    TranscriptResult,
    TranscriptSegment,
)


client = TestClient(app)


@pytest.fixture
def local_storage(monkeypatch, tmp_path: Path) -> LocalArtifactStorage:
    storage = LocalArtifactStorage(tmp_path / "store")
    monkeypatch.setattr(sources_module, "upload_storage", storage)
    return storage


def _register(size: int = 1024, duration: float | None = 95.5) -> dict:
    response = client.post(
        "/sources/upload",
        json={
            "filename": "clip.mp4",
            "content_type": "video/mp4",
            "size_bytes": size,
            "duration_seconds": duration,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_upload_registration_returns_a_direct_target_for_local_storage(local_storage) -> None:
    source = _register()

    assert source["type"] == "UPLOAD"
    assert source["status"] == "CREATED"
    assert source["metadata"]["upload"]["duration_seconds"] == 95.5
    assert source["upload"] == {"mode": "direct", "url": f"/sources/{source['id']}/content"}
    assert "processing_reference" not in source


def test_upload_registration_returns_a_signed_put_url_when_storage_offers_one(
    monkeypatch, local_storage
) -> None:
    monkeypatch.setattr(
        local_storage, "upload_url", lambda key, *, content_type: f"https://signed/{key}"
    )

    source = _register()

    assert source["upload"]["mode"] == "signed_put"
    assert source["upload"]["url"] == f"https://signed/uploads/{source['id']}.mp4"
    assert source["upload"]["headers"] == {"Content-Type": "video/mp4"}


def test_upload_registration_rejects_non_video_and_oversized_files(local_storage) -> None:
    bad_type = client.post(
        "/sources/upload",
        json={"filename": "notes.txt", "content_type": "text/plain", "size_bytes": 10},
    )
    assert bad_type.status_code == 422

    too_big = client.post(
        "/sources/upload",
        json={"filename": "big.mp4", "content_type": "video/mp4", "size_bytes": 10**12},
    )
    assert too_big.status_code == 422
    assert "MB" in too_big.json()["detail"]


def test_direct_content_upload_stores_the_file_and_marks_ready(local_storage) -> None:
    source = _register(size=11)

    put = client.put(
        f"/sources/{source['id']}/content",
        content=b"video-bytes",
        headers={"Content-Type": "video/mp4"},
    )

    assert put.status_code == 200
    assert put.json()["status"] == "READY"
    assert put.json()["metadata"]["media"] == {"provider": "upload"}
    stored = local_storage.root / "uploads" / f"{source['id']}.mp4"
    assert stored.read_bytes() == b"video-bytes"

    again = client.post(f"/sources/{source['id']}/uploaded")
    assert again.status_code == 200 and again.json()["status"] == "READY"


def test_confirming_before_the_object_exists_is_a_conflict(local_storage) -> None:
    source = _register()

    response = client.post(f"/sources/{source['id']}/uploaded")

    assert response.status_code == 409
    assert client.get(f"/sources/{source['id']}").json()["status"] == "CREATED"

    (local_storage.root / "uploads").mkdir(parents=True)
    (local_storage.root / "uploads" / f"{source['id']}.mp4").write_bytes(b"x")
    assert client.post(f"/sources/{source['id']}/uploaded").json()["status"] == "READY"


def test_upload_acquirer_serves_files_from_storage(tmp_path: Path) -> None:
    storage = LocalArtifactStorage(tmp_path / "store")
    (storage.root / "uploads").mkdir(parents=True)
    (storage.root / "uploads" / "abc.mp4").write_bytes(b"movie")
    url = upload_source_url("uploads/abc.mp4")
    assert is_upload_url(url) and url == "upload://uploads/abc.mp4"

    acquired = UploadAcquirer(storage).acquire(url, destination=tmp_path / "in.mp4")

    assert acquired.provider == "upload"
    assert acquired.path.read_bytes() == b"movie"

    with pytest.raises(AcquisitionError) as excinfo:
        UploadAcquirer(storage).acquire("upload://uploads/missing.mp4", destination=tmp_path / "x.mp4")
    assert excinfo.value.retryable is False


def test_routing_acquirer_dispatches_by_scheme(tmp_path: Path) -> None:
    calls = []

    class Default:
        name = "titan"

        def acquire(self, url, *, destination, progress=None):
            calls.append(url)
            destination.write_bytes(b"yt")
            from app.acquisition import AcquiredVideo

            return AcquiredVideo(path=destination, provider=self.name)

    storage = LocalArtifactStorage(tmp_path / "store")
    (storage.root / "uploads").mkdir(parents=True)
    (storage.root / "uploads" / "u.mp4").write_bytes(b"up")
    router = RoutingAcquirer(Default(), UploadAcquirer(storage))

    assert router.acquire("upload://uploads/u.mp4", destination=tmp_path / "a.mp4").provider == "upload"
    assert router.acquire("https://youtu.be/x", destination=tmp_path / "b.mp4").provider == "titan"
    assert calls == ["https://youtu.be/x"]


def test_caption_provider_skips_titan_for_uploads() -> None:
    class ExplodingTitan:
        def fetch_subtitles(self, url, *, language):
            raise AssertionError("must not be called for uploads")

    with pytest.raises(CaptionsUnavailableError):
        TitanCaptionProvider(ExplodingTitan()).fetch("upload://uploads/u.mp4", language="ko")


class StubTranscriptProcessor:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def process(self, source_url, *, start_seconds, end_seconds, language=None):
        self.urls.append(source_url)
        return TranscriptResult(
            provider="openai_whisper",
            language="ko",
            is_generated=True,
            source_start_seconds=start_seconds,
            source_end_seconds=end_seconds,
            segments=[
                TranscriptSegment(start_seconds=start_seconds, end_seconds=start_seconds + 3, text="업로드 음성")
            ],
            full_text="업로드 음성",
        )


class StubDispatcher:
    def enqueue(self, job_id, background_tasks) -> str:
        return f"queues/test/tasks/processing-{job_id}"

    def schedule_resume(self, job_id, *, delay_seconds, sequence) -> str:
        return "resume"


class AllowWorkerAuthenticator:
    def authenticate(self, authorization):
        assert authorization == "Bearer test-token"


def test_processing_job_for_an_upload_resolves_its_storage_url(monkeypatch, local_storage) -> None:
    repository = InMemoryProcessingJobRepository()
    processor = StubTranscriptProcessor()
    monkeypatch.setattr(jobs_module, "repository", repository)
    monkeypatch.setattr(jobs_module, "dispatcher", StubDispatcher())
    monkeypatch.setattr(jobs_module, "worker_authenticator", AllowWorkerAuthenticator())
    monkeypatch.setattr(jobs_module, "transcript_processor", processor)
    monkeypatch.setattr(jobs_module, "candidate_ranker", HeuristicRanker())
    source = _register(size=5)
    client.put(f"/sources/{source['id']}/content", content=b"movie", headers={"Content-Type": "video/mp4"})

    created = client.post(
        "/processing-jobs",
        json={
            "source_id": source["id"],
            "start_seconds": 0,
            "end_seconds": 90,
            "rights_confirmed": True,
            "transcript_language": "ko",
        },
    )

    assert created.status_code == 202, created.text
    job = created.json()
    worker = client.post(
        "/worker/process", json={"job_id": job["id"]}, headers={"Authorization": "Bearer test-token"}
    )
    assert worker.status_code == 200
    assert worker.json()["status"] == "COMPLETED"
    assert processor.urls == [f"upload://uploads/{source['id']}.mp4"]
    assert worker.json()["result"]["ranking"]["top_3"]


def test_manual_short_from_an_upload_uses_its_storage_url(monkeypatch, local_storage) -> None:
    monkeypatch.setattr(jobs_module, "repository", InMemoryProcessingJobRepository())
    monkeypatch.setattr(jobs_module, "dispatcher", StubDispatcher())
    source = _register(size=5)
    client.put(f"/sources/{source['id']}/content", content=b"movie", headers={"Content-Type": "video/mp4"})

    response = client.post(
        "/shorts",
        json={"source_id": source["id"], "start_seconds": 10, "end_seconds": 40, "rights_confirmed": True},
    )

    assert response.status_code == 202, response.text
    assert response.json()["youtube_url"] == f"upload://uploads/{source['id']}.mp4"
    assert response.json()["duration_seconds"] == 30

    missing = client.post(
        "/shorts", json={"source_id": str(uuid4()), "start_seconds": 0, "end_seconds": 30, "rights_confirmed": True}
    )
    assert missing.status_code == 422


def test_processing_job_without_url_needs_a_ready_upload(monkeypatch, local_storage) -> None:
    monkeypatch.setattr(jobs_module, "repository", InMemoryProcessingJobRepository())
    monkeypatch.setattr(jobs_module, "dispatcher", StubDispatcher())
    not_ready = _register()

    response = client.post(
        "/processing-jobs",
        json={"source_id": not_ready["id"], "start_seconds": 0, "end_seconds": 60, "rights_confirmed": True},
    )
    assert response.status_code == 422

    unknown = client.post(
        "/processing-jobs",
        json={"source_id": str(uuid4()), "start_seconds": 0, "end_seconds": 60, "rights_confirmed": True},
    )
    assert unknown.status_code == 422
