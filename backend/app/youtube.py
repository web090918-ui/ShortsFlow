import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import deno
import yt_dlp
from yt_dlp.utils import DownloadError


logger = logging.getLogger(__name__)


def _deno_runtime_path() -> str:
    bundled_runtime = Path(__file__).parent / ".runtime" / "deno"
    if bundled_runtime.is_file():
        return str(bundled_runtime)
    return deno.find_deno_bin()


class VideoSourceProviderError(Exception):
    """An actionable source preparation failure safe to return to the client."""


@dataclass(frozen=True)
class PreparedVideoSource:
    metadata: dict[str, Any]
    processing_reference: dict[str, Any]


class VideoSourceProvider(Protocol):
    def prepare(self, url: str) -> PreparedVideoSource: ...


class _YtDlpLogger:
    def debug(self, message: str) -> None:
        logger.debug("yt-dlp: %s", message)

    def info(self, message: str) -> None:
        logger.info("yt-dlp: %s", message)

    def warning(self, message: str) -> None:
        logger.warning("yt-dlp: %s", message)

    def error(self, message: str) -> None:
        logger.error("yt-dlp: %s", message)


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _select_audio_format(formats: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        item
        for item in formats
        if item.get("url")
        and item.get("acodec") not in (None, "none")
        and item.get("vcodec") == "none"
    ]
    if not candidates:
        candidates = [
            item
            for item in formats
            if item.get("url") and item.get("acodec") not in (None, "none")
        ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            item.get("ext") == "m4a",
            _number(item.get("abr")),
            _number(item.get("asr")),
        ),
    )


def _select_video_format(formats: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        item
        for item in formats
        if item.get("url") and item.get("vcodec") not in (None, "none")
    ]
    if not candidates:
        return None
    bounded = [item for item in candidates if 0 < _number(item.get("height")) <= 1080]
    if bounded:
        candidates = bounded
    return max(
        candidates,
        key=lambda item: (
            item.get("ext") == "mp4",
            _number(item.get("height")),
            item.get("acodec") not in (None, "none"),
            _number(item.get("tbr")),
        ),
    )


def _public_format(format_info: dict[str, Any]) -> dict[str, Any]:
    return {
        "format_id": format_info.get("format_id"),
        "ext": format_info.get("ext"),
        "protocol": format_info.get("protocol"),
        "width": format_info.get("width"),
        "height": format_info.get("height"),
        "audio_codec": format_info.get("acodec"),
        "video_codec": format_info.get("vcodec"),
    }


def _private_format(format_info: dict[str, Any]) -> dict[str, Any]:
    return {
        **_public_format(format_info),
        "url": format_info["url"],
        "http_headers": format_info.get("http_headers") or {},
    }


class YouTubeSourceProvider:
    def prepare(self, url: str) -> PreparedVideoSource:
        options = {
            "cachedir": False,
            "extractor_retries": 2,
            "js_runtimes": {"deno": {"path": _deno_runtime_path()}},
            "logger": _YtDlpLogger(),
            "noplaylist": True,
            "quiet": True,
            "retries": 2,
            "skip_download": True,
            "socket_timeout": 20,
        }

        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(url, download=False)
        except DownloadError as exc:
            logger.warning("YouTube extraction failed", exc_info=exc)
            raise VideoSourceProviderError(
                "YouTube 영상을 불러오지 못했습니다. 공개 영상인지 확인해 주세요."
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected YouTube extraction failure")
            raise VideoSourceProviderError(
                "YouTube Source 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
            ) from exc

        if not isinstance(info, dict) or not info.get("id"):
            raise VideoSourceProviderError("YouTube 영상 정보를 확인하지 못했습니다.")
        if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
            raise VideoSourceProviderError("라이브 또는 예정된 영상은 아직 지원하지 않습니다.")

        formats = [item for item in info.get("formats") or [] if isinstance(item, dict)]
        audio_format = _select_audio_format(formats)
        video_format = _select_video_format(formats)
        if audio_format is None or video_format is None:
            raise VideoSourceProviderError(
                "이 영상에서 처리 가능한 오디오와 비디오 스트림을 찾지 못했습니다."
            )

        resolved_at = datetime.now(timezone.utc).isoformat()
        video_id = str(info["id"])
        webpage_url = str(info.get("webpage_url") or url)
        metadata = {
            "youtube": {
                "video_id": video_id,
                "title": info.get("title"),
                "duration_seconds": info.get("duration"),
                "channel_id": info.get("channel_id"),
                "channel_title": info.get("channel") or info.get("uploader"),
                "thumbnail_url": info.get("thumbnail"),
                "upload_date": info.get("upload_date"),
                "view_count": info.get("view_count"),
                "live_status": info.get("live_status"),
            },
            "media": {
                "resolved_at": resolved_at,
                "video": _public_format(video_format),
                "audio": _public_format(audio_format),
            },
        }
        processing_reference = {
            "provider": "youtube",
            "video_id": video_id,
            "webpage_url": webpage_url,
            "resolved_at": resolved_at,
            "streams": {
                "video": _private_format(video_format),
                "audio": _private_format(audio_format),
            },
        }
        return PreparedVideoSource(
            metadata=metadata,
            processing_reference=processing_reference,
        )
