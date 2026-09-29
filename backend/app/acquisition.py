"""Full-video acquisition providers for the manual-range Short pipeline.

A provider only obtains the source file. Trimming and the 9:16 conversion live in
``app.video_processing`` so providers can be swapped without touching editing code.
"""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from app.youtube import _YtDlpLogger, _deno_runtime_path


logger = logging.getLogger(__name__)
ProgressCallback = Callable[[int], None]
DEFAULT_MAX_SOURCE_BYTES = 2 * 1024 * 1024 * 1024


class AcquisitionError(RuntimeError):
    """The source video could not be obtained. ``retryable`` guides the Worker."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class AcquiredVideo:
    path: Path
    provider: str
    title: str | None = None
    duration_seconds: float | None = None


class VideoAcquisitionProvider(Protocol):
    name: str

    def acquire(
        self,
        url: str,
        *,
        destination: Path,
        progress: ProgressCallback | None = None,
    ) -> AcquiredVideo: ...


def _report(progress: ProgressCallback | None, value: int) -> None:
    if progress is not None:
        progress(max(0, min(100, value)))


def download_to_file(
    url: str,
    destination: Path,
    *,
    max_bytes: int,
    timeout_seconds: float,
    progress: ProgressCallback | None = None,
    progress_range: tuple[int, int] = (0, 100),
) -> int:
    """Stream ``url`` into ``destination`` while enforcing a size ceiling."""
    request = Request(url, headers={"User-Agent": "ShortsFlow/0.1"})
    low, high = progress_range
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            content_length = response.headers.get("Content-Length")
            total = int(content_length) if content_length and content_length.isdigit() else 0
            if total > max_bytes:
                raise AcquisitionError(
                    "원본 영상이 처리 가능한 크기를 초과했습니다.", retryable=False
                )
            written = 0
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as output:
                while chunk := response.read(4 * 1024 * 1024):
                    written += len(chunk)
                    if written > max_bytes:
                        raise AcquisitionError(
                            "원본 영상이 처리 가능한 크기를 초과했습니다.", retryable=False
                        )
                    output.write(chunk)
                    if total > 0:
                        _report(progress, low + round((high - low) * written / total))
    except AcquisitionError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise AcquisitionError(
            "원본 영상을 내려받지 못했습니다. 잠시 후 다시 시도해 주세요."
        ) from exc
    if written == 0:
        raise AcquisitionError("내려받은 원본 영상이 비어 있습니다.")
    _report(progress, high)
    return written


class ApifyTitanProvider:
    """Acquire a full YouTube video through the Apify Titan YouTube Downloader actor.

    The actor is started asynchronously and polled, because a long video can exceed
    the synchronous Apify endpoint limit. Only the download link is read from the
    dataset; editing never happens on Apify.
    """

    name = "apify_titan"
    TERMINAL_RUN_STATUSES = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT", "TIMING-OUT"}

    def __init__(
        self,
        api_token: str,
        *,
        actor_id: str = "titan_network~titan-youtube-video-downloader",
        base_url: str = "https://api.apify.com",
        quality: str = "1080",
        run_timeout_seconds: float = 480,
        poll_interval_seconds: float = 5,
        max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
        request_timeout_seconds: float = 60,
        download_timeout_seconds: float = 600,
    ) -> None:
        self._api_token = api_token
        self._actor_id = actor_id
        self._base_url = base_url.rstrip("/")
        self._quality = quality
        self._run_timeout_seconds = run_timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._max_source_bytes = max_source_bytes
        self._request_timeout_seconds = request_timeout_seconds
        self._download_timeout_seconds = download_timeout_seconds

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        query = f"?{urlencode(params)}" if params else ""
        request = Request(
            f"{self._base_url}{path}{query}",
            method=method,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={
                "Authorization": f"Bearer {self._api_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "ShortsFlow/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self._request_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise AcquisitionError(
                    "영상 확보 서비스 인증에 실패했습니다.", retryable=False
                ) from exc
            if exc.code == 402:
                raise AcquisitionError(
                    "영상 확보 서비스 사용량 한도에 도달했습니다.", retryable=False
                ) from exc
            if exc.code == 404:
                raise AcquisitionError(
                    "영상 확보 서비스 구성이 올바르지 않습니다.", retryable=False
                ) from exc
            if exc.code == 429:
                raise AcquisitionError(
                    "영상 확보 서비스 요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요."
                ) from exc
            raise AcquisitionError(
                "영상 확보 서비스가 일시적으로 응답하지 않습니다."
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise AcquisitionError(
                "영상 확보 서비스에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요."
            ) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AcquisitionError(
                "영상 확보 서비스가 올바르지 않은 응답을 반환했습니다."
            ) from exc

    def _start_run(self, url: str) -> dict[str, Any]:
        payload = self._request(
            "POST",
            f"/v2/acts/{self._actor_id}/runs",
            body={
                "startUrls": [url],
                "outputType": "media",
                "quality": self._quality,
                "format": "mp4",
                "storageType": "apify",
                "maxConcurrency": 1,
                "maxWaitSec": int(self._run_timeout_seconds),
            },
        )
        run = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(run, dict) or not run.get("id"):
            raise AcquisitionError("영상 확보 작업을 시작하지 못했습니다.")
        return run

    def _wait_for_run(self, run_id: str, progress: ProgressCallback | None) -> dict[str, Any]:
        deadline = time.monotonic() + self._run_timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AcquisitionError("원본 영상 확보 시간이 초과되었습니다.")
            payload = self._request(
                "GET",
                f"/v2/actor-runs/{run_id}",
                params={"waitForFinish": str(int(min(60, max(1, remaining))))},
            )
            run = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(run, dict):
                raise AcquisitionError("영상 확보 작업 상태를 확인하지 못했습니다.")
            status = str(run.get("status") or "")
            if status == "SUCCEEDED":
                _report(progress, 40)
                return run
            if status in self.TERMINAL_RUN_STATUSES:
                raise AcquisitionError("영상 확보 서비스가 원본 영상을 가져오지 못했습니다.")
            elapsed_ratio = 1 - remaining / self._run_timeout_seconds
            _report(progress, 5 + round(30 * elapsed_ratio))
            time.sleep(min(self._poll_interval_seconds, max(0.0, remaining)))

    def _dataset_item(self, dataset_id: str) -> dict[str, Any]:
        items = self._request(
            "GET",
            f"/v2/datasets/{dataset_id}/items",
            params={"clean": "true", "format": "json"},
        )
        if not isinstance(items, list):
            raise AcquisitionError("영상 확보 결과를 읽지 못했습니다.")
        for item in items:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "completed").lower()
            file_url = item.get("downloadedFileUrl")
            if status == "completed" and isinstance(file_url, str) and file_url:
                return item
        for item in items:
            if isinstance(item, dict) and item.get("status") in {"failed", "timeout"}:
                raise AcquisitionError(
                    "YouTube 영상을 가져오지 못했습니다. 공개 영상인지 확인해 주세요.",
                    retryable=False,
                )
        raise AcquisitionError("영상 확보 결과에 다운로드 링크가 없습니다.")

    def acquire(
        self,
        url: str,
        *,
        destination: Path,
        progress: ProgressCallback | None = None,
    ) -> AcquiredVideo:
        _report(progress, 2)
        run = self._start_run(url)
        finished = self._wait_for_run(str(run["id"]), progress)
        dataset_id = finished.get("defaultDatasetId") or run.get("defaultDatasetId")
        if not isinstance(dataset_id, str) or not dataset_id:
            raise AcquisitionError("영상 확보 결과 저장소를 찾지 못했습니다.")
        item = self._dataset_item(dataset_id)
        file_url = str(item["downloadedFileUrl"])
        parsed = urlparse(file_url)
        if parsed.scheme != "https":
            raise AcquisitionError("안전하지 않은 다운로드 URL이 반환되었습니다.", retryable=False)
        download_to_file(
            file_url,
            destination,
            max_bytes=self._max_source_bytes,
            timeout_seconds=self._download_timeout_seconds,
            progress=progress,
            progress_range=(40, 100),
        )
        duration = item.get("durationSec")
        return AcquiredVideo(
            path=destination,
            provider=self.name,
            title=item.get("title") if isinstance(item.get("title"), str) else None,
            duration_seconds=float(duration) if isinstance(duration, (int, float)) else None,
        )


class YtDlpProvider:
    """Local-development fallback that downloads the full video with yt-dlp.

    Cloud IP ranges are routinely challenged by YouTube, so this provider is not the
    production path; it keeps the pipeline runnable without an Apify token.
    """

    name = "yt_dlp"

    def __init__(self, *, max_height: int = 1080) -> None:
        self._max_height = max_height

    def acquire(
        self,
        url: str,
        *,
        destination: Path,
        progress: ProgressCallback | None = None,
    ) -> AcquiredVideo:
        import yt_dlp
        from yt_dlp.utils import DownloadError

        destination.parent.mkdir(parents=True, exist_ok=True)
        stem = destination.with_suffix("")

        def hook(update: dict[str, Any]) -> None:
            if update.get("status") == "finished":
                _report(progress, 95)
                return
            downloaded = update.get("downloaded_bytes") or 0
            total = update.get("total_bytes") or update.get("total_bytes_estimate") or 0
            if downloaded and total:
                _report(progress, 5 + round(85 * downloaded / total))

        height = self._max_height
        options = {
            "cachedir": False,
            "extractor_retries": 2,
            "format": (
                f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/"
                f"b[height<={height}][ext=mp4]/bv*[height<={height}]+ba/b[height<={height}]/b"
            ),
            "js_runtimes": {"deno": {"path": _deno_runtime_path()}},
            "logger": _YtDlpLogger(),
            "merge_output_format": "mp4",
            "noplaylist": True,
            "outtmpl": f"{stem}.%(ext)s",
            "progress_hooks": [hook],
            "quiet": True,
            "retries": 2,
            "socket_timeout": 30,
        }
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(url, download=True)
        except DownloadError as exc:
            logger.warning("yt-dlp acquisition failed", exc_info=exc)
            if "Sign in to confirm you’re not a bot" in str(exc):
                raise AcquisitionError(
                    "YouTube가 현재 서버의 영상 요청을 제한했습니다. 다른 확보 공급자가 필요합니다.",
                    retryable=False,
                ) from exc
            raise AcquisitionError(
                "YouTube 영상을 가져오지 못했습니다. 공개 영상인지 확인해 주세요."
            ) from exc

        candidates = [
            path
            for path in destination.parent.glob(f"{stem.name}.*")
            if path.is_file() and path.suffix not in {".part", ".ytdl"}
        ]
        artifact = next((path for path in candidates if path.suffix == ".mp4"), None) or (
            candidates[0] if candidates else None
        )
        if artifact is None:
            raise AcquisitionError("내려받은 원본 영상 파일을 찾지 못했습니다.")
        if artifact != destination:
            artifact.replace(destination)
        _report(progress, 100)
        title = info.get("title") if isinstance(info, dict) else None
        duration = info.get("duration") if isinstance(info, dict) else None
        return AcquiredVideo(
            path=destination,
            provider=self.name,
            title=title if isinstance(title, str) else None,
            duration_seconds=float(duration) if isinstance(duration, (int, float)) else None,
        )
