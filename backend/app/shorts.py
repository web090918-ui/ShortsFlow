"""Public API for the manual-range Short: YouTube URL + start/end -> 9:16 MP4.

This router is a thin facade over the Task 04 processing-job infrastructure. It
creates a ``SHORT_RENDER`` job, exposes user-facing status, and serves or redirects
to the finished artifact.
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field, HttpUrl

from app.config import get_settings
from app.downloads import RenderTemplate
from app import processing_jobs as jobs
from app.processing_jobs import (
    ProcessingJobRecord,
    ProcessingJobStatus,
    ProcessingStep,
    _is_youtube_url,
    _now,
    enqueue_job,
)
from app.shorts_pipeline import ShortStage
from app.sources import SourceStatus, SourceType, repository as source_repository


router = APIRouter(prefix="/shorts", tags=["shorts"])


class ShortStatus(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


class CreateShortRequest(BaseModel):
    youtube_url: HttpUrl = Field(max_length=2048)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    rights_confirmed: bool = False
    template_id: RenderTemplate = RenderTemplate.CLEAN_CAPTION
    source_id: UUID | None = None


class ShortJobResponse(BaseModel):
    id: UUID
    status: ShortStatus
    progress: int = Field(ge=0, le=100)
    youtube_url: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    template_id: RenderTemplate
    download_url: str | None
    download_expires_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


_STAGE_STATUS = {
    ShortStage.DOWNLOADING.value: ShortStatus.DOWNLOADING,
    ShortStage.PROCESSING.value: ShortStatus.PROCESSING,
    ShortStage.UPLOADING.value: ShortStatus.UPLOADING,
}


def _short_result(job: ProcessingJobRecord) -> dict:
    result = job.result or {}
    short = result.get("short")
    return short if isinstance(short, dict) else {}


def _to_response(job: ProcessingJobRecord) -> ShortJobResponse:
    if job.status == ProcessingJobStatus.COMPLETED:
        short_status = ShortStatus.COMPLETED
    elif job.status == ProcessingJobStatus.FAILED:
        short_status = ShortStatus.FAILED
    elif job.status == ProcessingJobStatus.PROCESSING:
        short_status = _STAGE_STATUS.get(job.stage or "", ShortStatus.PROCESSING)
    else:
        short_status = ShortStatus.QUEUED

    download_url = None
    expires_at = None
    if short_status == ShortStatus.COMPLETED:
        short = _short_result(job)
        download_url = short.get("download_url") or f"/shorts/{job.id}/file"
        raw_expires = short.get("expires_at")
        if isinstance(raw_expires, str):
            expires_at = datetime.fromisoformat(raw_expires)

    return ShortJobResponse(
        id=job.id,
        status=short_status,
        progress=job.progress,
        youtube_url=job.source_url,
        start_seconds=job.start_seconds,
        end_seconds=job.end_seconds,
        duration_seconds=job.duration_seconds,
        template_id=job.template_id,
        download_url=download_url,
        download_expires_at=expires_at,
        error_message=job.error_message if short_status == ShortStatus.FAILED else None,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
    )


def _get_short_job(job_id: UUID) -> ProcessingJobRecord:
    # Read through the module so the repository configured at runtime is used.
    job = jobs.repository.get(job_id)
    if job is None or job.step != ProcessingStep.SHORT_RENDER:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Short job not found."
        )
    return job


@router.post("", response_model=ShortJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_short(
    payload: CreateShortRequest, background_tasks: BackgroundTasks
) -> ShortJobResponse:
    settings = get_settings()
    if not _is_youtube_url(payload.youtube_url):
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
    if duration <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="종료 시간은 시작 시간보다 커야 합니다.",
        )
    if duration > settings.shorts_max_clip_seconds:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"쇼츠 길이는 최대 {settings.shorts_max_clip_seconds}초까지 가능합니다.",
        )
    if payload.source_id is not None:
        source = source_repository.get(payload.source_id)
        if (
            source is not None
            and source.type == SourceType.YOUTUBE
            and source.status == SourceStatus.READY
        ):
            source_duration = source.metadata.get("youtube", {}).get("duration_seconds")
            if (
                isinstance(source_duration, (int, float))
                and payload.end_seconds > source_duration
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="선택한 종료 시간이 원본 영상 길이를 초과합니다.",
                )

    now = _now()
    job = ProcessingJobRecord(
        id=uuid4(),
        source_id=payload.source_id or uuid4(),
        source_url=str(payload.youtube_url),
        status=ProcessingJobStatus.QUEUED,
        step=ProcessingStep.SHORT_RENDER,
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
    return _to_response(enqueue_job(job, background_tasks))


@router.get("/{job_id}", response_model=ShortJobResponse)
def get_short(job_id: UUID) -> ShortJobResponse:
    return _to_response(_get_short_job(job_id))


@router.get("/{job_id}/file")
def download_short_file(job_id: UUID):
    job = _get_short_job(job_id)
    if job.status != ProcessingJobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="쇼츠 영상이 아직 준비되지 않았습니다.",
        )
    short = _short_result(job)
    signed_url = short.get("download_url")
    if isinstance(signed_url, str) and signed_url.startswith("https://"):
        return RedirectResponse(signed_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    local_path = short.get("local_path")
    if not isinstance(local_path, str) or not Path(local_path).is_file():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="쇼츠 영상을 더 이상 사용할 수 없습니다.",
        )
    start = round(job.start_seconds)
    end = round(job.end_seconds)
    return FileResponse(
        path=local_path,
        media_type="video/mp4",
        filename=f"cutpick-short-{start}-{end}.mp4",
    )
