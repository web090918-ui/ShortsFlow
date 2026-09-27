import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl

from app.config import Settings, get_settings
from app.downloads import MAX_RANGE_SECONDS, RenderTemplate


logger = logging.getLogger(__name__)
LEASE_SECONDS = 10 * 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProcessingJobStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ProcessingStep(str, Enum):
    PIPELINE_BOOTSTRAP = "PIPELINE_BOOTSTRAP"


class CreateProcessingJobRequest(BaseModel):
    source_id: UUID
    source_url: HttpUrl
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    rights_confirmed: bool = False
    template_id: RenderTemplate = RenderTemplate.CLEAN_CAPTION


class ProcessingJobResponse(BaseModel):
    id: UUID
    source_id: UUID
    status: ProcessingJobStatus
    step: ProcessingStep
    progress: int = Field(ge=0, le=100)
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    template_id: RenderTemplate
    attempt_count: int = Field(ge=0)
    error_message: str | None
    result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ProcessingJobRecord(ProcessingJobResponse):
    source_url: str
    task_name: str | None = None
    lease_expires_at: datetime | None = None


@dataclass(frozen=True)
class ClaimResult:
    job: ProcessingJobRecord
    acquired: bool
    retry_later: bool = False


class ProcessingJobRepository(Protocol):
    def save(self, job: ProcessingJobRecord) -> ProcessingJobRecord: ...

    def get(self, job_id: UUID) -> ProcessingJobRecord | None: ...

    def claim(self, job_id: UUID) -> ClaimResult | None: ...


class InMemoryProcessingJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[UUID, ProcessingJobRecord] = {}
        self._lock = threading.Lock()

    def save(self, job: ProcessingJobRecord) -> ProcessingJobRecord:
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: UUID) -> ProcessingJobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def claim(self, job_id: UUID) -> ClaimResult | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            now = _now()
            if job.status in {ProcessingJobStatus.COMPLETED, ProcessingJobStatus.FAILED}:
                return ClaimResult(job=job, acquired=False)
            if (
                job.status == ProcessingJobStatus.PROCESSING
                and job.lease_expires_at is not None
                and job.lease_expires_at > now
            ):
                return ClaimResult(job=job, acquired=False, retry_later=True)
            claimed = job.model_copy(
                update={
                    "status": ProcessingJobStatus.PROCESSING,
                    "progress": max(1, job.progress),
                    "attempt_count": job.attempt_count + 1,
                    "started_at": job.started_at or now,
                    "lease_expires_at": now + timedelta(seconds=LEASE_SECONDS),
                    "updated_at": now,
                }
            )
            self._jobs[job_id] = claimed
            return ClaimResult(job=claimed, acquired=True)


class FirestoreProcessingJobRepository:
    """Firestore adapter loaded only when the Cloud Run environment selects it."""

    def __init__(self, client: Any, collection: str = "processing_jobs") -> None:
        self._client = client
        self._collection = client.collection(collection)

    @staticmethod
    def _serialize(job: ProcessingJobRecord) -> dict[str, Any]:
        return job.model_dump(mode="json")

    @staticmethod
    def _deserialize(payload: dict[str, Any]) -> ProcessingJobRecord:
        return ProcessingJobRecord.model_validate(payload)

    def save(self, job: ProcessingJobRecord) -> ProcessingJobRecord:
        self._collection.document(str(job.id)).set(self._serialize(job))
        return job

    def get(self, job_id: UUID) -> ProcessingJobRecord | None:
        snapshot = self._collection.document(str(job_id)).get()
        if not snapshot.exists:
            return None
        return self._deserialize(snapshot.to_dict())

    def claim(self, job_id: UUID) -> ClaimResult | None:
        from google.cloud import firestore

        reference = self._collection.document(str(job_id))
        transaction = self._client.transaction()

        @firestore.transactional
        def claim_in_transaction(transaction: Any) -> ClaimResult | None:
            snapshot = reference.get(transaction=transaction)
            if not snapshot.exists:
                return None
            job = self._deserialize(snapshot.to_dict())
            now = _now()
            if job.status in {ProcessingJobStatus.COMPLETED, ProcessingJobStatus.FAILED}:
                return ClaimResult(job=job, acquired=False)
            if (
                job.status == ProcessingJobStatus.PROCESSING
                and job.lease_expires_at is not None
                and job.lease_expires_at > now
            ):
                return ClaimResult(job=job, acquired=False, retry_later=True)
            claimed = job.model_copy(
                update={
                    "status": ProcessingJobStatus.PROCESSING,
                    "progress": max(1, job.progress),
                    "attempt_count": job.attempt_count + 1,
                    "started_at": job.started_at or now,
                    "lease_expires_at": now + timedelta(seconds=LEASE_SECONDS),
                    "updated_at": now,
                }
            )
            transaction.set(reference, self._serialize(claimed))
            return ClaimResult(job=claimed, acquired=True)

        return claim_in_transaction(transaction)


class TaskDispatcher(Protocol):
    def enqueue(
        self,
        job_id: UUID,
        background_tasks: BackgroundTasks,
    ) -> str: ...


class LocalTaskDispatcher:
    def enqueue(self, job_id: UUID, background_tasks: BackgroundTasks) -> str:
        background_tasks.add_task(process_job, job_id, 0)
        return f"local://processing-jobs/{job_id}"


class CloudTasksDispatcher:
    def __init__(
        self,
        client: Any,
        *,
        project_id: str,
        location: str,
        queue: str,
        worker_url: str,
        service_account_email: str,
        audience: str,
    ) -> None:
        self._client = client
        self._parent = client.queue_path(project_id, location, queue)
        self._worker_url = worker_url.rstrip("/") + "/worker/process"
        self._service_account_email = service_account_email
        self._audience = audience

    def enqueue(self, job_id: UUID, background_tasks: BackgroundTasks) -> str:
        task_name = f"{self._parent}/tasks/processing-{job_id}"
        task = {
            "name": task_name,
            "http_request": {
                "http_method": "POST",
                "url": self._worker_url,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"job_id": str(job_id)}).encode("utf-8"),
                "oidc_token": {
                    "service_account_email": self._service_account_email,
                    "audience": self._audience,
                },
            },
            "dispatch_deadline": {"seconds": LEASE_SECONDS},
        }
        try:
            created = self._client.create_task(
                request={"parent": self._parent, "task": task}
            )
        except Exception as exc:
            if exc.__class__.__name__ == "AlreadyExists":
                return task_name
            raise
        return str(created.name)


class WorkerAuthenticator(Protocol):
    def authenticate(self, authorization: str | None) -> None: ...


class DisabledWorkerAuthenticator:
    def authenticate(self, authorization: str | None) -> None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Worker authentication is not configured.",
        )


class GoogleOidcWorkerAuthenticator:
    def __init__(self, *, audience: str, allowed_email: str) -> None:
        self._audience = audience
        self._allowed_email = allowed_email

    def authenticate(self, authorization: str | None) -> None:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A Google OIDC bearer token is required.",
            )
        token = authorization.removeprefix("Bearer ").strip()
        try:
            from google.auth.transport import requests as google_requests
            from google.oauth2 import id_token

            claims = id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                audience=self._audience,
            )
        except Exception as exc:
            logger.warning("Worker OIDC validation failed", exc_info=exc)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="The Worker token is invalid.",
            ) from exc
        if claims.get("email") != self._allowed_email or not claims.get(
            "email_verified", False
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The Worker identity is not allowed.",
            )


class WorkerRequest(BaseModel):
    job_id: UUID


def _require_settings(settings: Settings, *names: str) -> list[str]:
    values: list[str] = []
    for name in names:
        value = getattr(settings, name)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"SHORTSFLOW_{name.upper()} must be configured.")
        values.append(value)
    return values


def _repository_from_settings(settings: Settings) -> ProcessingJobRepository:
    if settings.job_repository_backend == "memory":
        return InMemoryProcessingJobRepository()
    from google.cloud import firestore

    project_id = _require_settings(settings, "gcp_project_id")[0]
    return FirestoreProcessingJobRepository(
        firestore.Client(project=project_id, database=settings.firestore_database)
    )


def _dispatcher_from_settings(settings: Settings) -> TaskDispatcher:
    if settings.task_dispatcher_backend == "local":
        return LocalTaskDispatcher()
    from google.cloud import tasks_v2

    project_id, worker_url, service_account = _require_settings(
        settings,
        "gcp_project_id",
        "worker_url",
        "worker_service_account_email",
    )
    audience = settings.worker_oidc_audience or worker_url
    return CloudTasksDispatcher(
        tasks_v2.CloudTasksClient(),
        project_id=project_id,
        location=settings.gcp_location,
        queue=settings.cloud_tasks_queue,
        worker_url=worker_url,
        service_account_email=service_account,
        audience=audience,
    )


def _authenticator_from_settings(settings: Settings) -> WorkerAuthenticator:
    if settings.worker_auth_mode == "disabled":
        return DisabledWorkerAuthenticator()
    worker_url, allowed_email = _require_settings(
        settings, "worker_url", "worker_service_account_email"
    )
    return GoogleOidcWorkerAuthenticator(
        audience=settings.worker_oidc_audience or worker_url,
        allowed_email=allowed_email,
    )


settings = get_settings()
repository: ProcessingJobRepository = _repository_from_settings(settings)
dispatcher: TaskDispatcher = _dispatcher_from_settings(settings)
worker_authenticator: WorkerAuthenticator = _authenticator_from_settings(settings)
router = APIRouter(tags=["processing-jobs"])


def _is_youtube_url(url: HttpUrl) -> bool:
    hostname = (url.host or "").lower()
    return (
        hostname == "youtu.be"
        or hostname == "youtube.com"
        or hostname.endswith(".youtube.com")
    )


def process_job(job_id: UUID, retry_count: int) -> ProcessingJobRecord | None:
    claim = repository.claim(job_id)
    if claim is None:
        return None
    if not claim.acquired:
        if claim.retry_later:
            raise RuntimeError("Processing job is already leased by another worker.")
        return claim.job

    job = claim.job
    try:
        # Task 04 validates durable dispatch and idempotent execution only.
        # Task 05 replaces this bootstrap result with transcript processing.
        completed = job.model_copy(
            update={
                "status": ProcessingJobStatus.COMPLETED,
                "progress": 100,
                "result": {"next_step": "TRANSCRIPT"},
                "error_message": None,
                "lease_expires_at": None,
                "completed_at": _now(),
                "updated_at": _now(),
            }
        )
        return repository.save(completed)
    except Exception as exc:
        terminal = retry_count + 1 >= settings.processing_max_attempts
        failed = job.model_copy(
            update={
                "status": (
                    ProcessingJobStatus.FAILED
                    if terminal
                    else ProcessingJobStatus.QUEUED
                ),
                "error_message": str(exc),
                "lease_expires_at": None,
                "updated_at": _now(),
            }
        )
        repository.save(failed)
        raise


@router.post(
    "/processing-jobs",
    response_model=ProcessingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_processing_job(
    payload: CreateProcessingJobRequest,
    background_tasks: BackgroundTasks,
) -> ProcessingJobRecord:
    if not _is_youtube_url(payload.source_url):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="YouTube 영상 URL을 입력해 주세요.",
        )
    if not payload.rights_confirmed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="원본 영상에 대한 소유권 또는 필요한 이용 허가를 확인해야 합니다.",
        )
    duration = payload.end_seconds - payload.start_seconds
    if duration <= 0 or duration > MAX_RANGE_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="처리 구간은 0초보다 길고 최대 60분이어야 합니다.",
        )

    now = _now()
    job = ProcessingJobRecord(
        id=uuid4(),
        source_id=payload.source_id,
        source_url=str(payload.source_url),
        status=ProcessingJobStatus.QUEUED,
        step=ProcessingStep.PIPELINE_BOOTSTRAP,
        progress=0,
        start_seconds=payload.start_seconds,
        end_seconds=payload.end_seconds,
        duration_seconds=duration,
        template_id=payload.template_id,
        attempt_count=0,
        error_message=None,
        result=None,
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )
    repository.save(job)
    try:
        task_name = dispatcher.enqueue(job.id, background_tasks)
    except Exception as exc:
        logger.exception("Failed to enqueue processing job", extra={"job_id": str(job.id)})
        failed = job.model_copy(
            update={
                "status": ProcessingJobStatus.FAILED,
                "error_message": "비동기 작업을 등록하지 못했습니다.",
                "updated_at": _now(),
            }
        )
        repository.save(failed)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="비동기 작업을 등록하지 못했습니다.",
        ) from exc
    return repository.save(job.model_copy(update={"task_name": task_name}))


@router.get("/processing-jobs/{job_id}", response_model=ProcessingJobResponse)
def get_processing_job(job_id: UUID) -> ProcessingJobRecord:
    job = repository.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processing job not found.",
        )
    return job


@router.post("/worker/process", response_model=ProcessingJobResponse)
def run_processing_worker(
    payload: WorkerRequest,
    authorization: str | None = Header(default=None),
    x_cloudtasks_taskretrycount: int = Header(default=0),
) -> ProcessingJobRecord:
    worker_authenticator.authenticate(authorization)
    try:
        job = process_job(payload.job_id, x_cloudtasks_taskretrycount)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processing job not found.",
        )
    return job
