"""Manual-range Short pipeline: acquire -> trim/9:16 -> store.

The pipeline is intentionally provider-agnostic. ``app.acquisition`` supplies the
source file, ``app.video_processing`` edits it, and the storage boundary below
publishes the result. Cloud Tasks orchestration stays in ``app.processing_jobs``.
"""

import logging
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol

from pydantic import BaseModel

from app.acquisition import (
    AcquisitionError,
    AcquisitionPendingError,
    VideoAcquisitionProvider,
    YtDlpProvider,
    titan_acquirer_from_settings,
)
from app.captions import CaptionCue, build_ass, select_cues
from app.config import Settings
from app.downloads import RenderTemplate
from app.source_media import SourceMediaRepository
from app.video_processing import FfmpegVideoProcessor, VideoProcessingError, VideoProcessor


logger = logging.getLogger(__name__)
RANGE_TOLERANCE_SECONDS = 0.5


class ShortStage(str, Enum):
    DOWNLOADING = "DOWNLOADING"
    PROCESSING = "PROCESSING"
    UPLOADING = "UPLOADING"


class ShortErrorCode(str, Enum):
    INVALID_TIME_RANGE = "INVALID_TIME_RANGE"
    SOURCE_DOWNLOAD_FAILED = "SOURCE_DOWNLOAD_FAILED"
    FFMPEG_FAILED = "FFMPEG_FAILED"
    TTS_FAILED = "TTS_FAILED"
    STORAGE_UPLOAD_FAILED = "STORAGE_UPLOAD_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ShortPipelineError(RuntimeError):
    """A classified pipeline failure. ``str(exc)`` is safe to show to the user."""

    def __init__(
        self, code: ShortErrorCode, message: str, *, retryable: bool = True
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class StoredArtifact:
    storage: str
    key: str
    download_url: str | None
    local_path: Path | None
    expires_at: datetime | None
    preview_url: str | None = None


class ArtifactStorage(Protocol):
    def store(self, file_path: Path, *, key: str, filename: str) -> StoredArtifact: ...

    def exists(self, key: str) -> bool:
        """Whether the stored artifact is still there (lifecycle rules may remove it)."""
        ...


class LocalArtifactStorage:
    """Keeps rendered Shorts on the local disk; the API serves them by job id."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def exists(self, key: str) -> bool:
        return (self._root / key).is_file()

    def store(self, file_path: Path, *, key: str, filename: str) -> StoredArtifact:
        destination = self._root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(file_path), str(destination))
        return StoredArtifact(
            storage="local",
            key=key,
            download_url=None,
            local_path=destination,
            expires_at=None,
        )


class GcsArtifactStorage:
    """Uploads to Cloud Storage and returns a V4 signed download URL."""

    def __init__(self, client: Any, bucket_name: str, *, ttl_seconds: int) -> None:
        self._bucket = client.bucket(bucket_name)
        self._ttl_seconds = ttl_seconds

    def exists(self, key: str) -> bool:
        try:
            return bool(self._bucket.blob(key).exists())
        except Exception as exc:  # network or permission trouble: report unavailable
            logger.warning("Could not check artifact %s: %s", key, exc)
            return False

    def _signed_url(self, blob: Any, filename: str, *, inline: bool = False) -> str:
        disposition = "inline" if inline else f'attachment; filename="{filename}"'
        options: dict[str, Any] = {
            "version": "v4",
            "expiration": timedelta(seconds=self._ttl_seconds),
            "method": "GET",
            "response_disposition": disposition,
            "response_type": "video/mp4",
        }
        try:
            return str(blob.generate_signed_url(**options))
        except (AttributeError, TypeError, ValueError):
            # Cloud Run credentials have no private key; sign through the IAM API.
            import google.auth
            from google.auth.transport import requests as google_requests

            credentials, _ = google.auth.default()
            credentials.refresh(google_requests.Request())
            return str(
                blob.generate_signed_url(
                    **options,
                    service_account_email=credentials.service_account_email,
                    access_token=credentials.token,
                )
            )

    def store(self, file_path: Path, *, key: str, filename: str) -> StoredArtifact:
        blob = self._bucket.blob(key)
        blob.upload_from_filename(str(file_path), content_type="video/mp4")
        return StoredArtifact(
            storage="gcs",
            key=key,
            download_url=self._signed_url(blob, filename),
            local_path=None,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self._ttl_seconds),
            # Same object, inline disposition, so the browser can play it in <video>.
            preview_url=self._signed_url(blob, filename, inline=True),
        )


class ShortArtifact(BaseModel):
    provider: str
    storage: str
    storage_key: str
    download_url: str | None
    preview_url: str | None = None
    local_path: str | None
    expires_at: datetime | None
    template_id: str | None = None
    captions_applied: int = 0
    source_title: str | None
    source_duration_seconds: float
    source_width: int | None
    source_height: int | None
    output_bytes: int


ProgressReporter = Callable[[ShortStage, int], None]


class ShortPipeline:
    def __init__(
        self,
        provider: VideoAcquisitionProvider,
        processor: VideoProcessor,
        storage: ArtifactStorage,
    ) -> None:
        self._provider = provider
        self._processor = processor
        self._storage = storage

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def storage(self) -> ArtifactStorage:
        return self._storage

    def run(
        self,
        *,
        job_id: str,
        source_url: str,
        start_seconds: float,
        end_seconds: float,
        report: ProgressReporter,
        captions: list[CaptionCue] | None = None,
        template: RenderTemplate | None = None,
    ) -> ShortArtifact:
        try:
            return self._run(
                job_id=job_id,
                source_url=source_url,
                captions=captions,
                template=template,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                report=report,
            )
        except ShortPipelineError:
            raise
        except AcquisitionPendingError:
            # Not a failure: the Worker defers the job and retries later.
            raise
        except AcquisitionError as exc:
            raise ShortPipelineError(
                ShortErrorCode.SOURCE_DOWNLOAD_FAILED, str(exc), retryable=exc.retryable
            ) from exc
        except VideoProcessingError as exc:
            logger.warning("Short render failed in FFmpeg: %s", exc)
            raise ShortPipelineError(
                ShortErrorCode.FFMPEG_FAILED, "쇼츠 영상을 편집하지 못했습니다."
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected Short pipeline failure", extra={"job_id": job_id})
            raise ShortPipelineError(
                ShortErrorCode.INTERNAL_ERROR, "쇼츠 생성 중 오류가 발생했습니다."
            ) from exc

    def _run(
        self,
        *,
        job_id: str,
        source_url: str,
        start_seconds: float,
        end_seconds: float,
        report: ProgressReporter,
        captions: list[CaptionCue] | None,
        template: RenderTemplate | None,
    ) -> ShortArtifact:
        # Temporary media lives only for this attempt and is removed on success or failure.
        with tempfile.TemporaryDirectory(
            prefix=f"shortsflow-short-{job_id}-", ignore_cleanup_errors=True
        ) as temp:
            temp_path = Path(temp)
            input_path = temp_path / "input.mp4"
            output_path = temp_path / "output.mp4"

            report(ShortStage.DOWNLOADING, 2)
            acquired = self._provider.acquire(
                source_url,
                destination=input_path,
                progress=lambda value: report(ShortStage.DOWNLOADING, 2 + value * 48 // 100),
            )

            info = self._processor.probe(acquired.path)
            if end_seconds > info.duration_seconds + RANGE_TOLERANCE_SECONDS:
                raise ShortPipelineError(
                    ShortErrorCode.INVALID_TIME_RANGE,
                    "선택한 종료 시간이 원본 영상 길이를 초과합니다.",
                    retryable=False,
                )

            report(ShortStage.PROCESSING, 55)
            clip_end = min(end_seconds, info.duration_seconds)
            subtitles_path = None
            captions_applied = 0
            if captions and template is not None:
                selected = select_cues(
                    captions, start_seconds=start_seconds, end_seconds=clip_end
                )
                if selected:
                    subtitles_path = temp_path / "captions.ass"
                    subtitles_path.write_text(
                        build_ass(
                            selected,
                            template=template,
                            clip_start_seconds=start_seconds,
                            clip_end_seconds=clip_end,
                        ),
                        encoding="utf-8",
                    )
                    captions_applied = len(selected)
            self._processor.trim_to_vertical(
                acquired.path,
                output_path,
                start_seconds=start_seconds,
                end_seconds=clip_end,
                subtitles_path=subtitles_path,
            )
            output_bytes = output_path.stat().st_size

            report(ShortStage.UPLOADING, 85)
            filename = f"cutpick-short-{round(start_seconds)}-{round(end_seconds)}.mp4"
            try:
                stored = self._storage.store(
                    output_path, key=f"shorts/{job_id}.mp4", filename=filename
                )
            except Exception as exc:
                logger.exception("Short artifact upload failed", extra={"job_id": job_id})
                raise ShortPipelineError(
                    ShortErrorCode.STORAGE_UPLOAD_FAILED,
                    "완성된 쇼츠를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.",
                ) from exc

        return ShortArtifact(
            provider=acquired.provider,
            storage=stored.storage,
            storage_key=stored.key,
            download_url=stored.download_url,
            preview_url=stored.preview_url,
            local_path=str(stored.local_path) if stored.local_path else None,
            expires_at=stored.expires_at,
            template_id=template.value if template is not None else None,
            captions_applied=captions_applied,
            source_title=acquired.title,
            source_duration_seconds=info.duration_seconds,
            source_width=info.width,
            source_height=info.height,
            output_bytes=output_bytes,
        )


def _acquisition_provider_from_settings(
    settings: Settings, media_cache: SourceMediaRepository
) -> VideoAcquisitionProvider:
    selection = settings.shorts_acquisition_provider
    if selection == "auto":
        selection = "apify_titan" if settings.apify_api_token is not None else "yt_dlp"
    if selection == "apify_titan":
        # Resumable and cached: long sources defer the job instead of blocking the Worker.
        titan = titan_acquirer_from_settings(settings, media_cache)
        if titan is None:
            raise RuntimeError("SHORTSFLOW_APIFY_API_TOKEN must be configured.")
        return titan
    return YtDlpProvider()


def _storage_from_settings(settings: Settings) -> ArtifactStorage:
    if settings.shorts_storage_backend == "local":
        root = (
            Path(settings.shorts_local_storage_dir)
            if settings.shorts_local_storage_dir
            else Path(tempfile.gettempdir()) / "shortsflow-shorts"
        )
        return LocalArtifactStorage(root)
    from google.cloud import storage

    if not settings.gcs_bucket:
        raise RuntimeError("SHORTSFLOW_GCS_BUCKET must be configured.")
    return GcsArtifactStorage(
        storage.Client(project=settings.gcp_project_id),
        settings.gcs_bucket,
        ttl_seconds=settings.shorts_download_ttl_seconds,
    )


def short_pipeline_from_settings(
    settings: Settings, media_cache: SourceMediaRepository
) -> ShortPipeline:
    return ShortPipeline(
        _acquisition_provider_from_settings(settings, media_cache),
        FfmpegVideoProcessor(),
        _storage_from_settings(settings),
    )
