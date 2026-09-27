import logging
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, HttpUrl

from app.sources import SourceStatus, SourceType, repository as source_repository
from app.config import get_settings
from app.tunelio import TunelioClient
from app.youtube import (
    VideoRangeDownloader,
    VideoSourceProviderError,
    YouTubeRangeDownloader,
)


MAX_RANGE_SECONDS = 60 * 60
logger = logging.getLogger(__name__)


class DownloadStatus(str, Enum):
    QUEUED = "QUEUED"
    DOWNLOADING = "DOWNLOADING"
    READY = "READY"
    FAILED = "FAILED"


class RenderTemplate(str, Enum):
    CLEAN_CAPTION = "CLEAN_CAPTION"
    BOLD_HIGHLIGHT = "BOLD_HIGHLIGHT"
    MINIMAL = "MINIMAL"


class RangeDownloadRequest(BaseModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    rights_confirmed: bool = False
    template_id: RenderTemplate = RenderTemplate.CLEAN_CAPTION
    source_url: HttpUrl | None = None


class RangeDownloadResponse(BaseModel):
    id: UUID
    source_id: UUID
    status: DownloadStatus
    progress: int = Field(ge=0, le=100)
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    template_id: RenderTemplate
    error_message: str | None
    download_url: str | None
    download_expires_at: int | None = None
    created_at: datetime
    updated_at: datetime


class RangeDownloadRecord(RangeDownloadResponse):
    source_url: str
    artifact_path: Path | None = None


class InMemoryDownloadRepository:
    def __init__(self) -> None:
        self._jobs: dict[UUID, RangeDownloadRecord] = {}
        self._lock = threading.Lock()

    def save(self, job: RangeDownloadRecord) -> RangeDownloadRecord:
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: UUID) -> RangeDownloadRecord | None:
        with self._lock:
            return self._jobs.get(job_id)


repository = InMemoryDownloadRepository()
range_downloader: VideoRangeDownloader = YouTubeRangeDownloader()


def _tunelio_client_from_settings() -> TunelioClient | None:
    settings = get_settings()
    if settings.tunelio_api_key is None:
        return None
    return TunelioClient(
        settings.tunelio_api_key.get_secret_value(),
        base_url=settings.tunelio_base_url,
    )


tunelio_client = _tunelio_client_from_settings()
router = APIRouter(tags=["downloads"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _save_progress(job_id: UUID, progress: int) -> None:
    job = repository.get(job_id)
    if job is None or job.status == DownloadStatus.FAILED:
        return
    repository.save(
        job.model_copy(
            update={
                "status": DownloadStatus.DOWNLOADING,
                "progress": min(99, max(job.progress, progress)),
                "updated_at": _now(),
            }
        )
    )


def _run_download(job_id: UUID) -> None:
    job = repository.get(job_id)
    if job is None:
        return

    output_directory = Path(tempfile.gettempdir()) / "shortsflow-media" / str(job.id)
    _save_progress(job_id, 1)
    try:
        artifact = range_downloader.download(
            job.source_url,
            start_seconds=job.start_seconds,
            end_seconds=job.end_seconds,
            output_directory=output_directory,
            progress=lambda value: _save_progress(job_id, value),
        )
    except VideoSourceProviderError as exc:
        shutil.rmtree(output_directory, ignore_errors=True)
        current = repository.get(job_id) or job
        repository.save(
            current.model_copy(
                update={
                    "status": DownloadStatus.FAILED,
                    "error_message": str(exc),
                    "updated_at": _now(),
                }
            )
        )
        return
    except Exception:
        logger.exception(
            "Unexpected selected-range download failure",
            extra={"job_id": str(job_id)},
        )
        shutil.rmtree(output_directory, ignore_errors=True)
        current = repository.get(job_id) or job
        repository.save(
            current.model_copy(
                update={
                    "status": DownloadStatus.FAILED,
                    "error_message": "선택 구간 처리 중 오류가 발생했습니다.",
                    "updated_at": _now(),
                }
            )
        )
        return

    current = repository.get(job_id) or job
    repository.save(
        current.model_copy(
            update={
                "status": DownloadStatus.READY,
                "progress": 100,
                "artifact_path": artifact,
                "download_url": f"/downloads/{job_id}/file",
                "updated_at": _now(),
            }
        )
    )


@router.post(
    "/sources/{source_id}/downloads",
    response_model=RangeDownloadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_range_download(
    source_id: UUID,
    payload: RangeDownloadRequest,
    background_tasks: BackgroundTasks,
) -> RangeDownloadRecord:
    source = source_repository.get(source_id)
    if source is None:
        if tunelio_client is None or payload.source_url is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Source not found."
            )
        source_url = str(payload.source_url)
        hostname = (payload.source_url.host or "").lower()
        if not (
            hostname == "youtu.be"
            or hostname == "youtube.com"
            or hostname.endswith(".youtube.com")
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="YouTube 영상 URL을 입력해 주세요.",
            )
        source_duration = None
    elif source.type != SourceType.YOUTUBE or source.status != SourceStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="준비가 완료된 YouTube Source만 구간 다운로드할 수 있습니다.",
        )
    else:
        source_url = source.url or ""
        source_duration = source.metadata.get("youtube", {}).get("duration_seconds")
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
    if duration > MAX_RANGE_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="한 번에 최대 60분까지 선택할 수 있습니다.",
        )

    if isinstance(source_duration, (int, float)) and payload.end_seconds > source_duration:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="선택한 종료 시간이 원본 영상 길이를 초과합니다.",
        )

    now = _now()
    job = RangeDownloadRecord(
        id=uuid4(),
        source_id=source_id,
        source_url=source_url,
        status=DownloadStatus.QUEUED,
        progress=0,
        start_seconds=payload.start_seconds,
        end_seconds=payload.end_seconds,
        duration_seconds=duration,
        template_id=payload.template_id,
        error_message=None,
        download_url=None,
        created_at=now,
        updated_at=now,
    )
    repository.save(job)
    if tunelio_client is not None:
        try:
            reference = tunelio_client.create_range(
                job.source_url,
                start_seconds=job.start_seconds,
                end_seconds=job.end_seconds,
                quality="480p",
            )
        except VideoSourceProviderError as exc:
            return repository.save(
                job.model_copy(
                    update={
                        "status": DownloadStatus.FAILED,
                        "error_message": str(exc),
                        "updated_at": _now(),
                    }
                )
            )
        return repository.save(
            job.model_copy(
                update={
                    "status": DownloadStatus.READY,
                    "progress": 100,
                    "download_url": reference.url,
                    "download_expires_at": reference.expires_at,
                    "updated_at": _now(),
                }
            )
        )

    background_tasks.add_task(_run_download, job.id)
    return job


@router.get("/downloads/{job_id}", response_model=RangeDownloadResponse)
def get_range_download(job_id: UUID) -> RangeDownloadRecord:
    job = repository.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Download job not found.",
        )
    return job


@router.get("/downloads/{job_id}/file", response_class=FileResponse)
def download_range_file(job_id: UUID) -> FileResponse:
    job = repository.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Download job not found.",
        )
    if job.status != DownloadStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="선택 구간 파일이 아직 준비되지 않았습니다.",
        )
    if job.artifact_path is None or not job.artifact_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="선택 구간 파일을 더 이상 사용할 수 없습니다.",
        )

    start = round(job.start_seconds)
    end = round(job.end_seconds)
    return FileResponse(
        path=job.artifact_path,
        media_type="video/mp4",
        filename=f"shortsflow-{start}-{end}.mp4",
    )
