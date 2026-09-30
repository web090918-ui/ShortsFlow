"""Public API for rendering a Short: manual range or a ranked candidate -> 9:16 MP4.

This router is a thin facade over the Task 04 processing-job infrastructure. It
creates a ``SHORT_RENDER`` job, exposes user-facing status, and serves or redirects
to the finished artifact for download and inline preview.
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field, HttpUrl, model_validator

from app import processing_jobs as jobs
from app.candidates import clean_caption_text
from app.config import get_settings
from app.downloads import RenderTemplate
from app.processing_jobs import (
    ProcessingJobRecord,
    ProcessingJobStatus,
    ProcessingStep,
    _is_youtube_url,
    _now,
    enqueue_job,
)
from app.product_content import ContentAngle
from app.product_pipeline import render_input_for
from app.products import ProductFacts
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
    """Either a manual range (``youtube_url`` + times) or a ranked candidate."""

    youtube_url: HttpUrl | None = Field(default=None, max_length=2048)
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, gt=0)
    rights_confirmed: bool = False
    template_id: RenderTemplate | None = None
    source_id: UUID | None = None
    processing_job_id: UUID | None = None
    candidate_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _one_input_mode(self) -> "CreateShortRequest":
        from_candidate = self.processing_job_id is not None or self.candidate_id is not None
        manual = self.youtube_url is not None or self.start_seconds is not None or (
            self.end_seconds is not None
        )
        if from_candidate and manual:
            raise ValueError("processing_job_id/candidate_id와 직접 구간 입력은 함께 쓸 수 없습니다.")
        if from_candidate and (self.processing_job_id is None or not self.candidate_id):
            raise ValueError("processing_job_id와 candidate_id를 함께 입력해 주세요.")
        if not from_candidate and (
            self.youtube_url is None or self.start_seconds is None or self.end_seconds is None
        ):
            raise ValueError("youtube_url, start_seconds, end_seconds를 입력해 주세요.")
        return self


ArtifactState = Literal["pending", "ready", "expired", "unavailable", "failed"]


class ShortJobResponse(BaseModel):
    id: UUID
    status: ShortStatus
    progress: int = Field(ge=0, le=100)
    youtube_url: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    template_id: RenderTemplate
    candidate_id: str | None
    processing_job_id: UUID | None
    download_url: str | None
    preview_url: str | None
    download_expires_at: datetime | None
    # pending: still rendering; ready: downloadable; expired: link TTL passed;
    # unavailable: artifact removed from storage; failed: render failed.
    artifact_state: ArtifactState
    captions_applied: int = 0
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


def _artifact_state(job: ProcessingJobRecord, short_status: "ShortStatus") -> ArtifactState:
    if short_status == ShortStatus.FAILED:
        return "failed"
    if short_status != ShortStatus.COMPLETED:
        return "pending"
    short = _short_result(job)
    raw_expires = short.get("expires_at")
    if isinstance(raw_expires, str) and datetime.fromisoformat(raw_expires) <= _now():
        return "expired"
    storage = getattr(jobs.short_pipeline, "storage", None)
    key = short.get("storage_key")
    if storage is not None and isinstance(key, str) and not storage.exists(key):
        return "unavailable"
    return "ready"


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
    elif job.stage:
        # Queued again while waiting on the media provider: still "downloading" to the user.
        short_status = _STAGE_STATUS.get(job.stage, ShortStatus.QUEUED)
    else:
        short_status = ShortStatus.QUEUED

    download_url = None
    preview_url = None
    expires_at = None
    captions_applied = 0
    artifact_state = _artifact_state(job, short_status)
    if short_status == ShortStatus.COMPLETED:
        short = _short_result(job)
        raw_expires = short.get("expires_at")
        if isinstance(raw_expires, str):
            expires_at = datetime.fromisoformat(raw_expires)
        if isinstance(short.get("captions_applied"), int):
            captions_applied = short["captions_applied"]
        if artifact_state == "ready":
            download_url = short.get("download_url") or f"/shorts/{job.id}/file"
            preview_url = short.get("preview_url") or f"/shorts/{job.id}/file?inline=true"

    render_input = job.render_input or {}
    processing_job_id = render_input.get("processing_job_id")
    return ShortJobResponse(
        id=job.id,
        status=short_status,
        progress=job.progress,
        youtube_url=job.source_url,
        start_seconds=job.start_seconds,
        end_seconds=job.end_seconds,
        duration_seconds=job.duration_seconds,
        template_id=job.template_id,
        candidate_id=render_input.get("candidate_id"),
        processing_job_id=UUID(processing_job_id) if isinstance(processing_job_id, str) else None,
        download_url=download_url,
        preview_url=preview_url,
        download_expires_at=expires_at,
        artifact_state=artifact_state,
        captions_applied=captions_applied,
        error_message=job.error_message if short_status == ShortStatus.FAILED else None,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
    )


def _get_short_job(job_id: UUID) -> ProcessingJobRecord:
    # Read through the module so the repository configured at runtime is used.
    job = jobs.repository.get(job_id)
    if job is None or job.step not in {ProcessingStep.SHORT_RENDER, ProcessingStep.PRODUCT_RENDER}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Short job not found."
        )
    return job


class CreateProductShortRequest(BaseModel):
    """Render a product Short from a READY product Source and one content angle."""

    source_id: UUID
    angle_id: str = Field(min_length=1, max_length=64)
    template_id: RenderTemplate = RenderTemplate.CLEAN_CAPTION
    cta_url: HttpUrl | None = None
    terms_confirmed: bool = False


@router.post("/product", response_model=ShortJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_product_short(
    payload: CreateProductShortRequest, background_tasks: BackgroundTasks
) -> ShortJobResponse:
    if not payload.terms_confirmed:
        raise _unprocessable("쿠팡 파트너스 약관에 따라 상품 정보와 이미지를 사용함을 확인해야 합니다.")
    source = source_repository.get(payload.source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")
    if source.type != SourceType.PRODUCT or source.status != SourceStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="준비가 완료된 상품 Source만 쇼츠로 만들 수 있습니다.",
        )
    content = source.metadata.get("product_content")
    if not isinstance(content, dict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="먼저 콘텐츠 앵글을 생성해 주세요.",
        )
    angle = next(
        (
            item
            for item in content.get("angles", [])
            if isinstance(item, dict) and item.get("id") == payload.angle_id
        ),
        None,
    )
    if angle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angle not found.")
    facts = ProductFacts.model_validate(source.metadata["product"])
    angle_model = ContentAngle.model_validate(angle)

    now = _now()
    job = ProcessingJobRecord(
        id=uuid4(),
        source_id=source.id,
        source_url=source.url or facts.product_url,
        status=ProcessingJobStatus.QUEUED,
        step=ProcessingStep.PRODUCT_RENDER,
        progress=0,
        start_seconds=0,
        end_seconds=1,
        duration_seconds=1,
        template_id=payload.template_id,
        attempt_count=0,
        error_message=None,
        result=None,
        render_input=render_input_for(
            facts,
            angle_model,
            cta_url=str(payload.cta_url) if payload.cta_url else None,
            content_generator=str(content.get("generator") or "unknown"),
        ),
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )
    return _to_response(enqueue_job(job, background_tasks))


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def _resolve_candidate(
    payload: CreateShortRequest,
) -> tuple[str, float, float, RenderTemplate, UUID, dict[str, Any]]:
    """Derive URL, range, template, and captions from a completed analysis job."""
    analysis = jobs.repository.get(payload.processing_job_id)  # type: ignore[arg-type]
    if analysis is None or analysis.step == ProcessingStep.SHORT_RENDER:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Processing job not found."
        )
    if analysis.status != ProcessingJobStatus.COMPLETED or not analysis.result:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="후보 분석이 완료된 뒤에 쇼츠를 만들 수 있습니다.",
        )
    candidate_set = analysis.result.get("candidates") or {}
    candidate = next(
        (
            item
            for item in candidate_set.get("items", [])
            if isinstance(item, dict) and item.get("id") == payload.candidate_id
        ),
        None,
    )
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found."
        )
    transcript = analysis.result.get("transcript") or {}
    captions = []
    for segment in transcript.get("segments", []):
        if not isinstance(segment, dict):
            continue
        if (
            segment.get("end_seconds", 0) <= candidate["start_seconds"]
            or segment.get("start_seconds", 0) >= candidate["end_seconds"]
        ):
            continue
        # Sound tags and speaker marks are not speech; keep them off the screen too.
        text = clean_caption_text(str(segment.get("text") or ""))
        if not text:
            continue
        captions.append(
            {
                "start_seconds": segment["start_seconds"],
                "end_seconds": segment["end_seconds"],
                "text": text,
            }
        )
    template = payload.template_id or analysis.template_id
    render_input = {
        "processing_job_id": str(analysis.id),
        "candidate_id": candidate["id"],
        "candidate_index": candidate.get("index"),
        "captions": captions,
    }
    return (
        analysis.source_url,
        float(candidate["start_seconds"]),
        float(candidate["end_seconds"]),
        template,
        analysis.source_id,
        render_input,
    )


@router.post("", response_model=ShortJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_short(
    payload: CreateShortRequest, background_tasks: BackgroundTasks
) -> ShortJobResponse:
    settings = get_settings()
    if not payload.rights_confirmed:
        raise _unprocessable("원본 영상에 대한 소유권 또는 필요한 이용 허가를 확인해야 합니다.")

    render_input: dict[str, Any] | None = None
    if payload.processing_job_id is not None:
        source_url, start, end, template, source_id, render_input = _resolve_candidate(payload)
    else:
        assert payload.youtube_url is not None
        assert payload.start_seconds is not None and payload.end_seconds is not None
        if not _is_youtube_url(payload.youtube_url):
            raise _unprocessable("YouTube 영상 URL을 입력해 주세요.")
        source_url = str(payload.youtube_url)
        start, end = payload.start_seconds, payload.end_seconds
        template = payload.template_id or RenderTemplate.CLEAN_CAPTION
        source_id = payload.source_id or uuid4()
        if payload.source_id is not None:
            source = source_repository.get(payload.source_id)
            if (
                source is not None
                and source.type == SourceType.YOUTUBE
                and source.status == SourceStatus.READY
            ):
                source_duration = source.metadata.get("youtube", {}).get("duration_seconds")
                if isinstance(source_duration, (int, float)) and end > source_duration:
                    raise _unprocessable("선택한 종료 시간이 원본 영상 길이를 초과합니다.")

    duration = end - start
    if duration <= 0:
        raise _unprocessable("종료 시간은 시작 시간보다 커야 합니다.")
    if duration > settings.shorts_max_clip_seconds:
        raise _unprocessable(
            f"쇼츠 길이는 최대 {settings.shorts_max_clip_seconds}초까지 가능합니다."
        )

    now = _now()
    job = ProcessingJobRecord(
        id=uuid4(),
        source_id=source_id,
        source_url=source_url,
        status=ProcessingJobStatus.QUEUED,
        step=ProcessingStep.SHORT_RENDER,
        progress=0,
        start_seconds=start,
        end_seconds=end,
        duration_seconds=duration,
        template_id=template,
        attempt_count=0,
        error_message=None,
        result=None,
        render_input=render_input,
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
def download_short_file(job_id: UUID, inline: bool = False):
    job = _get_short_job(job_id)
    if job.status != ProcessingJobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="쇼츠 영상이 아직 준비되지 않았습니다.",
        )
    artifact_state = _artifact_state(job, ShortStatus.COMPLETED)
    if artifact_state == "expired":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="다운로드 링크가 만료되었습니다. 쇼츠를 다시 만들어 주세요.",
        )
    if artifact_state == "unavailable":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="쇼츠 영상이 보관 기간이 지나 삭제되었습니다. 다시 만들어 주세요.",
        )
    short = _short_result(job)
    signed_url = short.get("preview_url" if inline else "download_url")
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
        content_disposition_type="inline" if inline else "attachment",
    )
