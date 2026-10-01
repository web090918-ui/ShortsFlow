"""Per-account work history (Task 12A): everything the signed-in user created."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app import processing_jobs as jobs
from app import sources
from app.auth import UserRecord, credits, current_user
from app.credits import CreditEntry
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


class CreditSummary(BaseModel):
    balance: int
    costs: dict[str, int]
    entries: list[CreditEntry]


class ProjectSummary(BaseModel):
    """One card per source video: everything made from it, rolled up."""

    source_id: UUID
    title: str
    source_type: str
    source_url: str
    thumbnail_url: str | None
    channel_title: str | None
    duration_seconds: float | None
    status: Literal["completed", "processing", "failed"]
    shorts_count: int
    analyses_count: int
    created_at: datetime
    updated_at: datetime


class ProjectList(BaseModel):
    items: list[ProjectSummary]


class ProjectDetail(BaseModel):
    project: ProjectSummary
    items: list[WorkItem]


def _describe_url(url: str) -> str:
    if url.startswith("upload://"):
        return "업로드한 영상"
    return url


def _project_summary(source_id: UUID, group: list[ProcessingJobRecord]) -> ProjectSummary:
    source = sources.repository.get(source_id)
    metadata: dict[str, Any] = source.metadata if source is not None else {}
    youtube = metadata.get("youtube") if isinstance(metadata.get("youtube"), dict) else {}
    upload = metadata.get("upload") if isinstance(metadata.get("upload"), dict) else {}
    product = metadata.get("product") if isinstance(metadata.get("product"), dict) else {}
    newest = group[0]
    title = (
        youtube.get("title")
        or product.get("title")
        or upload.get("filename")
        or newest.title
        or _describe_url(newest.source_url)
    )
    renders = {ProcessingStep.SHORT_RENDER, ProcessingStep.PRODUCT_RENDER}
    active = {ProcessingJobStatus.QUEUED, ProcessingJobStatus.PROCESSING}
    if any(job.status in active for job in group):
        status_label: Literal["completed", "processing", "failed"] = "processing"
    elif all(job.status == ProcessingJobStatus.FAILED for job in group):
        status_label = "failed"
    else:
        status_label = "completed"
    return ProjectSummary(
        source_id=source_id,
        title=str(title),
        source_type=source.type.value if source is not None else "UNKNOWN",
        source_url=newest.source_url,
        thumbnail_url=youtube.get("thumbnail_url") or product.get("image_url"),
        channel_title=youtube.get("channel_title"),
        duration_seconds=youtube.get("duration_seconds") or upload.get("duration_seconds"),
        status=status_label,
        shorts_count=sum(
            1
            for job in group
            if job.step in renders and job.status == ProcessingJobStatus.COMPLETED
        ),
        analyses_count=sum(1 for job in group if job.step not in renders),
        created_at=min(job.created_at for job in group),
        updated_at=max(job.updated_at for job in group),
    )


def _grouped_by_source(user_id: UUID, *, limit: int) -> dict[UUID, list[ProcessingJobRecord]]:
    groups: dict[UUID, list[ProcessingJobRecord]] = {}
    for job in jobs.repository.list_for_user(user_id, limit=limit):
        groups.setdefault(job.source_id, []).append(job)
    return groups


def _work_item(job: ProcessingJobRecord) -> WorkItem:
    if job.step in {ProcessingStep.SHORT_RENDER, ProcessingStep.PRODUCT_RENDER}:
        return WorkItem(kind="short", created_at=job.created_at, short=_to_response(job))
    return WorkItem(kind="analysis", created_at=job.created_at, analysis=_analysis_summary(job))


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


@router.get("/credits", response_model=CreditSummary)
def my_credits(user: UserRecord | None = Depends(current_user)) -> CreditSummary:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")
    balance = credits.ensure_signup_grant(user.id)
    return CreditSummary(
        balance=balance,
        costs={
            "analysis_per_minute": credits.analysis_per_minute,
            "manual_short_per_minute": credits.manual_short_per_minute,
            "candidate_render": credits.candidate_render_cost,
            "product_short": credits.product_short_cost,
            "signup_grant": credits.signup_grant,
        },
        entries=credits.ledger.entries(user.id, limit=50),
    )


@router.get("/jobs", response_model=WorkList)
def my_jobs(limit: int = 50, user: UserRecord | None = Depends(current_user)) -> WorkList:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")
    return WorkList(
        items=[
            _work_item(job)
            for job in jobs.repository.list_for_user(user.id, limit=max(1, min(limit, 200)))
        ]
    )


@router.get("/projects", response_model=ProjectList)
def my_projects(limit: int = 200, user: UserRecord | None = Depends(current_user)) -> ProjectList:
    """Projects = source videos the user worked on, newest activity first."""
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")
    groups = _grouped_by_source(user.id, limit=max(1, min(limit, 500)))
    projects = [_project_summary(source_id, group) for source_id, group in groups.items()]
    projects.sort(key=lambda project: project.updated_at, reverse=True)
    return ProjectList(items=projects)


@router.get("/projects/{source_id}", response_model=ProjectDetail)
def my_project(source_id: UUID, user: UserRecord | None = Depends(current_user)) -> ProjectDetail:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")
    group = _grouped_by_source(user.id, limit=500).get(source_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return ProjectDetail(
        project=_project_summary(source_id, group), items=[_work_item(job) for job in group]
    )
