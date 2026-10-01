"""Per-account work history (Task 12A): everything the signed-in user created."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app import processing_jobs as jobs
from app.auth import UserRecord, current_user
from app.processing_jobs import ProcessingJobRecord, ProcessingJobStatus, ProcessingStep
from app.shorts import ShortJobResponse, _to_response


router = APIRouter(prefix="/me", tags=["me"])


class AnalysisSummary(BaseModel):
    id: UUID
    status: ProcessingJobStatus
    step: ProcessingStep
    progress: int
    source_url: str
    start_seconds: float
    end_seconds: float
    transcript_language: str
    top_hooks: list[str]
    candidate_count: int
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class WorkItem(BaseModel):
    kind: Literal["short", "analysis"]
    created_at: datetime
    short: ShortJobResponse | None = None
    analysis: AnalysisSummary | None = None


class WorkList(BaseModel):
    items: list[WorkItem]


def _analysis_summary(job: ProcessingJobRecord) -> AnalysisSummary:
    result: dict[str, Any] = job.result or {}
    ranking = result.get("ranking") or {}
    candidates = result.get("candidates") or {}
    top = ranking.get("top_3") if isinstance(ranking.get("top_3"), list) else []
    return AnalysisSummary(
        id=job.id,
        status=job.status,
        step=job.step,
        progress=job.progress,
        source_url=job.source_url,
        start_seconds=job.start_seconds,
        end_seconds=job.end_seconds,
        transcript_language=job.transcript_language,
        top_hooks=[str(item.get("hook_text", "")) for item in top if isinstance(item, dict)][:3],
        candidate_count=len(candidates.get("items", [])) if isinstance(candidates, dict) else 0,
        error_message=job.error_message if job.status == ProcessingJobStatus.FAILED else None,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.get("/jobs", response_model=WorkList)
def my_jobs(limit: int = 50, user: UserRecord | None = Depends(current_user)) -> WorkList:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")
    items: list[WorkItem] = []
    for job in jobs.repository.list_for_user(user.id, limit=max(1, min(limit, 200))):
        if job.step in {ProcessingStep.SHORT_RENDER, ProcessingStep.PRODUCT_RENDER}:
            items.append(WorkItem(kind="short", created_at=job.created_at, short=_to_response(job)))
        else:
            items.append(
                WorkItem(kind="analysis", created_at=job.created_at, analysis=_analysis_summary(job))
            )
    return WorkList(items=items)
