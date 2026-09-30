from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field, HttpUrl

from app.acquisition import AcquisitionError, titan_provider_from_settings
from app.product_content import (
    ContentGenerationError,
    ProductContentGenerator,
    product_content_generator_from_settings,
)
from app.products import ProductFacts, ProductSourceError, prepare_product
from app.youtube import VideoSourceProvider, VideoSourceProviderError, YouTubeSourceProvider
from app.config import get_settings


class SourceType(str, Enum):
    YOUTUBE = "YOUTUBE"
    PRODUCT = "PRODUCT"
    UPLOAD = "UPLOAD"


class SourceStatus(str, Enum):
    CREATED = "CREATED"
    PREPARING = "PREPARING"
    READY = "READY"
    FAILED = "FAILED"


class SourceUrlRequest(BaseModel):
    url: HttpUrl = Field(max_length=2048)


class SourceResponse(BaseModel):
    id: UUID
    user_id: UUID | None
    type: SourceType
    url: str | None
    status: SourceStatus
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SourceRecord(SourceResponse):
    processing_reference: dict[str, Any] | None = None


class SourceRepository(Protocol):
    def save(self, source: SourceRecord) -> SourceRecord: ...

    def get(self, source_id: UUID) -> SourceRecord | None: ...


class InMemorySourceRepository:
    """Task 02 storage adapter. Replace it when persistent storage is selected."""

    def __init__(self) -> None:
        self._sources: dict[UUID, SourceRecord] = {}

    def save(self, source: SourceRecord) -> SourceRecord:
        self._sources[source.id] = source
        return source

    def get(self, source_id: UUID) -> SourceRecord | None:
        return self._sources.get(source_id)


YOUTUBE_HOSTS = {"youtube.com", "youtu.be"}
VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}


def _hostname(url: HttpUrl) -> str:
    hostname = (url.host or "").lower()
    for prefix in ("www.", "m."):
        if hostname.startswith(prefix):
            hostname = hostname[len(prefix) :]
    return hostname


def _is_youtube_host(hostname: str) -> bool:
    return hostname in YOUTUBE_HOSTS or hostname.endswith(".youtube.com")


def _is_youtube_video_url(url: str, hostname: str) -> bool:
    parsed = urlparse(url)
    if hostname == "youtu.be":
        return bool(parsed.path.strip("/"))
    if parsed.path == "/watch":
        return bool(parse_qs(parsed.query).get("v", [""])[0])
    parts = [part for part in parsed.path.split("/") if part]
    return len(parts) >= 2 and parts[0] in {"embed", "live", "shorts"}


def classify_source_url(url: HttpUrl) -> SourceType:
    normalized_url = str(url)
    hostname = _hostname(url)
    if _is_youtube_host(hostname):
        if not _is_youtube_video_url(normalized_url, hostname):
            raise HTTPException(
                status_code=422,
                detail="Enter a supported YouTube video URL.",
            )
        return SourceType.YOUTUBE
    return SourceType.PRODUCT


def _new_source(
    source_type: SourceType,
    *,
    url: str | None,
    metadata: dict[str, Any],
) -> SourceRecord:
    now = datetime.now(timezone.utc)
    return SourceRecord(
        id=uuid4(),
        user_id=None,
        type=source_type,
        url=url,
        status=SourceStatus.CREATED,
        metadata=metadata,
        created_at=now,
        updated_at=now,
    )


repository: SourceRepository = InMemorySourceRepository()


def _youtube_provider_from_settings() -> VideoSourceProvider:
    # Apify Titan is the production metadata provider; yt-dlp remains the local default.
    titan = titan_provider_from_settings(get_settings())
    return titan if titan is not None else YouTubeSourceProvider()


youtube_provider: VideoSourceProvider = _youtube_provider_from_settings()
product_content_generator: ProductContentGenerator = product_content_generator_from_settings(
    get_settings()
)
router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_url_source(payload: SourceUrlRequest, prepare: bool = False) -> SourceResponse:
    source_type = classify_source_url(payload.url)
    source = _new_source(
        source_type,
        url=str(payload.url),
        metadata={"hostname": _hostname(payload.url)},
    )
    repository.save(source)
    if prepare and source.type in {SourceType.YOUTUBE, SourceType.PRODUCT}:
        return prepare_source(source.id)
    return source


@router.post(
    "/upload",
    response_model=SourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_upload_source(file: UploadFile = File(...)) -> SourceResponse:
    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()
    content_type = file.content_type or "application/octet-stream"

    if not filename or (
        not content_type.startswith("video/") and extension not in VIDEO_EXTENSIONS
    ):
        raise HTTPException(
            status_code=422,
            detail="Upload a supported video file.",
        )
    if file.size == 0:
        raise HTTPException(
            status_code=422,
            detail="The uploaded video file is empty.",
        )

    source = _new_source(
        SourceType.UPLOAD,
        url=None,
        metadata={
            "filename": filename,
            "content_type": content_type,
            "size_bytes": file.size,
        },
    )
    await file.close()
    return repository.save(source)


@router.get("/{source_id}", response_model=SourceResponse)
def get_source(source_id: UUID) -> SourceResponse:
    source = repository.get(source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")
    return source


class ProductContentRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=500)
    refresh: bool = False


@router.post("/{source_id}/product-content", response_model=SourceResponse)
def generate_product_content(source_id: UUID, payload: ProductContentRequest) -> SourceRecord:
    """Task 10: selling points and three content angles for a READY product Source."""
    source = repository.get(source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")
    if source.type != SourceType.PRODUCT or source.status != SourceStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="준비가 완료된 상품 Source만 콘텐츠를 만들 수 있습니다.",
        )
    if source.metadata.get("product_content") and not payload.refresh:
        return source
    facts = ProductFacts.model_validate(source.metadata["product"])
    try:
        content = product_content_generator.generate(facts, notes=payload.notes)
    except ContentGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    metadata = dict(source.metadata)
    metadata["product_content"] = content.model_dump(mode="json")
    return repository.save(
        source.model_copy(update={"metadata": metadata, "updated_at": datetime.now(timezone.utc)})
    )


@router.post("/{source_id}/prepare", response_model=SourceResponse)
def prepare_source(source_id: UUID) -> SourceRecord:
    source = repository.get(source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")
    if source.type not in {SourceType.YOUTUBE, SourceType.PRODUCT}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only YouTube and Product Sources can be prepared.",
        )
    if source.status == SourceStatus.READY:
        return source
    if source.status == SourceStatus.PREPARING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Source preparation is already in progress.",
        )

    preparing = source.model_copy(
        update={"status": SourceStatus.PREPARING, "updated_at": datetime.now(timezone.utc)}
    )
    repository.save(preparing)

    try:
        if source.type == SourceType.PRODUCT:
            prepared = prepare_product(preparing.url or "")
        else:
            prepared = youtube_provider.prepare(preparing.url or "")
    except (VideoSourceProviderError, AcquisitionError, ProductSourceError) as exc:
        failed_metadata = dict(preparing.metadata)
        failed_metadata["processing_error"] = str(exc)
        failed = preparing.model_copy(
            update={
                "status": SourceStatus.FAILED,
                "metadata": failed_metadata,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        repository.save(failed)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    ready_metadata = dict(preparing.metadata)
    ready_metadata.pop("processing_error", None)
    ready_metadata.update(prepared.metadata)
    ready = preparing.model_copy(
        update={
            "status": SourceStatus.READY,
            "metadata": ready_metadata,
            "processing_reference": prepared.processing_reference,
            "updated_at": datetime.now(timezone.utc),
        }
    )
    return repository.save(ready)
