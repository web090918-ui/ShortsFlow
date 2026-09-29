from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.processing_jobs as jobs_module
from app.main import app
from app.processing_jobs import (
    CloudTasksDispatcher,
    InMemoryProcessingJobRepository,
    ProcessingJobStatus,
)
from app.transcripts import TranscriptResult, TranscriptSegment


client = TestClient(app)


class StubTranscriptProcessor:
    def process(
        self, source_url, *, start_seconds, end_seconds, language=None
    ) -> TranscriptResult:
        assert language == "ko"
        return TranscriptResult(
            provider="apify_titan",
            language="ko",
            is_generated=True,
            source_start_seconds=start_seconds,
            source_end_seconds=end_seconds,
            segments=[
                TranscriptSegment(
                    start_seconds=start_seconds,
                    end_seconds=min(start_seconds + 2, end_seconds),
                    text="테스트 자막",
                )
            ],
            full_text="테스트 자막",
        )


@pytest.fixture(autouse=True)
def stub_transcript_processor(monkeypatch):
    monkeypatch.setattr(
        jobs_module, "transcript_processor", StubTranscriptProcessor()
    )


class StubDispatcher:
    def enqueue(self, job_id, background_tasks) -> str:
        return f"queues/test/tasks/processing-{job_id}"


class AllowWorkerAuthenticator:
    def authenticate(self, authorization: str | None) -> None:
        assert authorization == "Bearer test-token"


def _payload() -> dict:
    return {
        "source_id": str(uuid4()),
        "source_url": "https://www.youtube.com/watch?v=source123",
        "start_seconds": 60,
        "end_seconds": 180,
        "rights_confirmed": True,
        "template_id": "CLEAN_CAPTION",
    }


def test_creates_and_reads_queued_processing_job(monkeypatch) -> None:
    repository = InMemoryProcessingJobRepository()
    monkeypatch.setattr(jobs_module, "repository", repository)
    monkeypatch.setattr(jobs_module, "dispatcher", StubDispatcher())

    response = client.post("/processing-jobs", json=_payload())

    assert response.status_code == 202
    created = response.json()
    assert created["status"] == "QUEUED"
    assert created["step"] == "TRANSCRIPT"
    assert created["transcript_language"] == "ko"
    assert created["duration_seconds"] == 120

    read_response = client.get(f"/processing-jobs/{created['id']}")
    assert read_response.status_code == 200
    assert read_response.json() == created


def test_worker_is_idempotent_for_duplicate_delivery(monkeypatch) -> None:
    repository = InMemoryProcessingJobRepository()
    monkeypatch.setattr(jobs_module, "repository", repository)
    monkeypatch.setattr(jobs_module, "dispatcher", StubDispatcher())
    monkeypatch.setattr(
        jobs_module, "worker_authenticator", AllowWorkerAuthenticator()
    )
    created = client.post("/processing-jobs", json=_payload()).json()

    first = client.post(
        "/worker/process",
        json={"job_id": created["id"]},
        headers={"Authorization": "Bearer test-token"},
    )
    second = client.post(
        "/worker/process",
        json={"job_id": created["id"]},
        headers={"Authorization": "Bearer test-token"},
    )

    assert first.status_code == 200
    assert first.json()["status"] == "COMPLETED"
    assert first.json()["result"]["next_step"] == "CANDIDATE"
    assert first.json()["result"]["transcript"]["provider"] == "apify_titan"
    assert first.json()["attempt_count"] == 1
    assert second.status_code == 200
    assert second.json()["attempt_count"] == 1


def test_rejects_job_without_rights_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(
        jobs_module, "repository", InMemoryProcessingJobRepository()
    )
    monkeypatch.setattr(jobs_module, "dispatcher", StubDispatcher())
    payload = _payload()
    payload["rights_confirmed"] = False

    response = client.post("/processing-jobs", json=payload)

    assert response.status_code == 422


def test_active_processing_lease_requests_retry(monkeypatch) -> None:
    repository = InMemoryProcessingJobRepository()
    monkeypatch.setattr(jobs_module, "repository", repository)
    monkeypatch.setattr(jobs_module, "dispatcher", StubDispatcher())
    monkeypatch.setattr(
        jobs_module, "worker_authenticator", AllowWorkerAuthenticator()
    )
    created = client.post("/processing-jobs", json=_payload()).json()
    claimed = repository.claim(UUID(created["id"]))
    assert claimed is not None and claimed.acquired

    response = client.post(
        "/worker/process",
        json={"job_id": created["id"]},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 409


class FakeCloudTasksClient:
    def __init__(self) -> None:
        self.request = None

    def queue_path(self, project, location, queue) -> str:
        return f"projects/{project}/locations/{location}/queues/{queue}"

    def create_task(self, request):
        self.request = request
        return type("CreatedTask", (), {"name": request["task"]["name"]})()


def test_cloud_tasks_dispatcher_uses_deterministic_oidc_task() -> None:
    fake_client = FakeCloudTasksClient()
    dispatcher = CloudTasksDispatcher(
        fake_client,
        project_id="project-1",
        location="asia-northeast3",
        queue="shortsflow-processing",
        worker_url="https://worker.example",
        service_account_email="tasks@project-1.iam.gserviceaccount.com",
        audience="https://worker.example",
    )
    job_id = uuid4()

    task_name = dispatcher.enqueue(job_id, background_tasks=None)  # type: ignore[arg-type]

    assert task_name.endswith(f"/tasks/processing-{job_id}")
    request = fake_client.request
    assert request is not None
    http_request = request["task"]["http_request"]
    assert http_request["url"] == "https://worker.example/worker/process"
    assert http_request["oidc_token"] == {
        "service_account_email": "tasks@project-1.iam.gserviceaccount.com",
        "audience": "https://worker.example",
    }
    assert str(job_id).encode() in http_request["body"]


def test_completed_job_is_terminal(monkeypatch) -> None:
    repository = InMemoryProcessingJobRepository()
    monkeypatch.setattr(jobs_module, "repository", repository)
    monkeypatch.setattr(jobs_module, "dispatcher", StubDispatcher())
    monkeypatch.setattr(
        jobs_module, "worker_authenticator", AllowWorkerAuthenticator()
    )
    created = client.post("/processing-jobs", json=_payload()).json()
    completed = client.post(
        "/worker/process",
        json={"job_id": created["id"]},
        headers={"Authorization": "Bearer test-token"},
    ).json()

    stored = repository.get(UUID(created["id"]))
    assert stored is not None
    assert stored.status == ProcessingJobStatus.COMPLETED
    assert stored.completed_at is not None
    assert completed["progress"] == 100
