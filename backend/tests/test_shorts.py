from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.processing_jobs as jobs_module
from app.main import app
from app.processing_jobs import InMemoryProcessingJobRepository
from app.shorts_pipeline import ShortArtifact, ShortErrorCode, ShortPipelineError, ShortStage


client = TestClient(app)


class StubDispatcher:
    def enqueue(self, job_id, background_tasks) -> str:
        return f"queues/test/tasks/processing-{job_id}"


class AllowWorkerAuthenticator:
    def authenticate(self, authorization: str | None) -> None:
        assert authorization == "Bearer test-token"


class StubShortPipeline:
    def __init__(self, tmp_path: Path, *, error: Exception | None = None) -> None:
        self.tmp_path = tmp_path
        self.error = error
        self.calls: list[dict] = []

    def run(self, *, job_id, source_url, start_seconds, end_seconds, report):
        self.calls.append(
            {"job_id": job_id, "url": source_url, "start": start_seconds, "end": end_seconds}
        )
        report(ShortStage.DOWNLOADING, 10)
        if self.error is not None:
            raise self.error
        report(ShortStage.PROCESSING, 60)
        report(ShortStage.UPLOADING, 90)
        output = self.tmp_path / f"{job_id}.mp4"
        output.write_bytes(b"short-bytes")
        return ShortArtifact(
            provider="stub",
            storage="local",
            storage_key=f"shorts/{job_id}.mp4",
            download_url=None,
            local_path=str(output),
            expires_at=None,
            source_title="Sample",
            source_duration_seconds=600,
            source_width=1920,
            source_height=1080,
            output_bytes=11,
        )


@pytest.fixture(autouse=True)
def isolated_jobs(monkeypatch):
    repository = InMemoryProcessingJobRepository()
    monkeypatch.setattr(jobs_module, "repository", repository)
    monkeypatch.setattr(jobs_module, "dispatcher", StubDispatcher())
    monkeypatch.setattr(jobs_module, "worker_authenticator", AllowWorkerAuthenticator())
    return repository


def _payload(**overrides) -> dict:
    payload = {
        "youtube_url": "https://www.youtube.com/watch?v=abc123",
        "start_seconds": 135,
        "end_seconds": 185,
        "rights_confirmed": True,
    }
    payload.update(overrides)
    return payload


def _run_worker(job_id: str, retry_count: int = 0):
    return client.post(
        "/worker/process",
        json={"job_id": job_id},
        headers={
            "Authorization": "Bearer test-token",
            "X-CloudTasks-TaskRetryCount": str(retry_count),
        },
    )


def test_creates_queued_short_job() -> None:
    response = client.post("/shorts", json=_payload())

    assert response.status_code == 202
    created = response.json()
    assert created["status"] == "queued"
    assert created["progress"] == 0
    assert created["duration_seconds"] == 50
    assert created["template_id"] == "CLEAN_CAPTION"
    assert created["download_url"] is None

    read = client.get(f"/shorts/{created['id']}")
    assert read.status_code == 200
    assert read.json() == created

    # The underlying processing job is the Task 04 record with the new step.
    job = client.get(f"/processing-jobs/{created['id']}").json()
    assert job["step"] == "SHORT_RENDER"


@pytest.mark.parametrize(
    "overrides, expected_detail",
    [
        ({"rights_confirmed": False}, "소유권"),
        ({"start_seconds": 50, "end_seconds": 50}, "종료 시간은 시작 시간보다"),
        ({"start_seconds": 0, "end_seconds": 181}, "최대 180초"),
        ({"youtube_url": "https://example.com/video"}, "YouTube 영상 URL"),
    ],
)
def test_rejects_invalid_requests(overrides, expected_detail) -> None:
    response = client.post("/shorts", json=_payload(**overrides))

    assert response.status_code == 422
    assert expected_detail in response.json()["detail"]


def test_rejects_negative_start() -> None:
    response = client.post("/shorts", json=_payload(start_seconds=-1))

    assert response.status_code == 422


def test_worker_completes_short_and_serves_file(monkeypatch, tmp_path: Path) -> None:
    pipeline = StubShortPipeline(tmp_path)
    monkeypatch.setattr(jobs_module, "short_pipeline", pipeline)
    created = client.post("/shorts", json=_payload()).json()

    worker = _run_worker(created["id"])
    assert worker.status_code == 200
    assert worker.json()["status"] == "COMPLETED"
    assert worker.json()["result"]["next_step"] == "DOWNLOAD"
    assert pipeline.calls == [
        {
            "job_id": created["id"],
            "url": "https://www.youtube.com/watch?v=abc123",
            "start": 135,
            "end": 185,
        }
    ]

    short = client.get(f"/shorts/{created['id']}").json()
    assert short["status"] == "completed"
    assert short["progress"] == 100
    assert short["download_url"] == f"/shorts/{created['id']}/file"
    assert short["error_message"] is None

    file_response = client.get(short["download_url"])
    assert file_response.status_code == 200
    assert file_response.headers["content-type"] == "video/mp4"
    assert "cutpick-short-135-185.mp4" in file_response.headers["content-disposition"]
    assert file_response.content == b"short-bytes"

    # Duplicate delivery does not rerun the pipeline.
    _run_worker(created["id"])
    assert len(pipeline.calls) == 1


def test_stage_is_exposed_while_processing(monkeypatch, isolated_jobs) -> None:
    created = client.post("/shorts", json=_payload()).json()
    claimed = isolated_jobs.claim(__import__("uuid").UUID(created["id"]))
    assert claimed is not None and claimed.acquired
    isolated_jobs.save(claimed.job.model_copy(update={"stage": "UPLOADING", "progress": 90}))

    short = client.get(f"/shorts/{created['id']}").json()

    assert short["status"] == "uploading"
    assert short["progress"] == 90


def test_non_retryable_failure_marks_job_failed_immediately(monkeypatch, tmp_path) -> None:
    error = ShortPipelineError(
        ShortErrorCode.INVALID_TIME_RANGE, "선택한 종료 시간이 원본 영상 길이를 초과합니다.",
        retryable=False,
    )
    monkeypatch.setattr(jobs_module, "short_pipeline", StubShortPipeline(tmp_path, error=error))
    created = client.post("/shorts", json=_payload()).json()

    worker = _run_worker(created["id"])

    assert worker.status_code == 200
    assert worker.json()["status"] == "FAILED"
    assert worker.json()["error_code"] == "INVALID_TIME_RANGE"
    short = client.get(f"/shorts/{created['id']}").json()
    assert short["status"] == "failed"
    assert short["error_message"] == "선택한 종료 시간이 원본 영상 길이를 초과합니다."
    assert short["download_url"] is None


def test_retryable_failure_requeues_until_last_attempt(monkeypatch, tmp_path) -> None:
    error = ShortPipelineError(ShortErrorCode.SOURCE_DOWNLOAD_FAILED, "다운로드 실패")
    monkeypatch.setattr(jobs_module, "short_pipeline", StubShortPipeline(tmp_path, error=error))
    created = client.post("/shorts", json=_payload()).json()

    first = _run_worker(created["id"], retry_count=0)
    assert first.status_code == 409
    job = client.get(f"/processing-jobs/{created['id']}").json()
    assert job["status"] == "QUEUED"
    assert job["error_code"] == "SOURCE_DOWNLOAD_FAILED"

    last = _run_worker(created["id"], retry_count=2)
    assert last.status_code == 409
    short = client.get(f"/shorts/{created['id']}").json()
    assert short["status"] == "failed"
    assert short["error_message"] == "다운로드 실패"


def test_file_download_requires_completed_job() -> None:
    created = client.post("/shorts", json=_payload()).json()

    response = client.get(f"/shorts/{created['id']}/file")

    assert response.status_code == 409


def test_unknown_short_job_returns_404() -> None:
    assert client.get(f"/shorts/{uuid4()}").status_code == 404
    assert client.get(f"/shorts/{uuid4()}/file").status_code == 404
