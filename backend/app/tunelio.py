import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from app.youtube import PreparedVideoSource, VideoSourceProviderError


@dataclass(frozen=True)
class TunelioRangeReference:
    url: str
    expires_at: int | None
    filename: str | None


class TunelioClient:
    """Small server-side client for the two Tunelio endpoints used in Task 03B."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://tunelio.dev",
        timeout_seconds: float = 30,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def _get(self, path: str, **params: str) -> dict[str, Any]:
        request_url = f"{self._base_url}{path}?{urlencode(params)}"
        request = Request(
            request_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
                "User-Agent": "ShortsFlow/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                error_payload = json.loads(exc.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                error_payload = {}
            message = error_payload.get("message")
            if exc.code == 401:
                message = "Tunelio API 키가 올바르지 않습니다."
            elif exc.code == 402:
                message = "Tunelio 크레딧이 부족합니다."
            elif exc.code == 404:
                message = "공개 상태의 YouTube 영상을 찾을 수 없습니다."
            elif exc.code == 429:
                message = "Tunelio 요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요."
            elif exc.code in {500, 503}:
                message = "영상 확보 서비스가 일시적으로 응답하지 않습니다."
            raise VideoSourceProviderError(
                str(message or "영상 확보 요청에 실패했습니다.")
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise VideoSourceProviderError(
                "영상 확보 서비스에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요."
            ) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise VideoSourceProviderError(
                "영상 확보 서비스가 올바르지 않은 응답을 반환했습니다."
            ) from exc

        if not isinstance(payload, dict):
            raise VideoSourceProviderError(
                "영상 확보 서비스가 올바르지 않은 응답을 반환했습니다."
            )
        return payload

    def prepare(self, url: str) -> PreparedVideoSource:
        payload = self._get("/info", url=url)
        duration = payload.get("duration_seconds")
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise VideoSourceProviderError("YouTube 영상 길이를 확인하지 못했습니다.")

        formats = payload.get("formats")
        public_formats = formats if isinstance(formats, list) else []
        return PreparedVideoSource(
            metadata={
                "youtube": {
                    "title": payload.get("title"),
                    "duration_seconds": duration,
                    "thumbnail_url": payload.get("thumbnail"),
                },
                "media": {
                    "provider": "tunelio",
                    "available_formats": public_formats,
                },
            },
            processing_reference={
                "provider": "tunelio",
                "webpage_url": url,
            },
        )

    def create_range(
        self,
        url: str,
        *,
        start_seconds: float,
        end_seconds: float,
        quality: str = "480p",
    ) -> TunelioRangeReference:
        payload = self._get("/create", url=url, quality=quality)
        tunnel_url = payload.get("url")
        if not isinstance(tunnel_url, str):
            raise VideoSourceProviderError("선택 구간 다운로드 URL을 받지 못했습니다.")

        parsed = urlparse(tunnel_url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not (
            hostname == "tunelio.dev" or hostname.endswith(".tunelio.dev")
        ):
            raise VideoSourceProviderError("안전하지 않은 다운로드 URL이 반환되었습니다.")

        separator = "&" if parsed.query else "?"
        range_query = urlencode(
            {"start": str(start_seconds), "end": str(end_seconds)}
        )
        range_url = f"{tunnel_url}{separator}{range_query}"
        expires = payload.get("expires")
        return TunelioRangeReference(
            url=range_url,
            expires_at=expires if isinstance(expires, int) else None,
            filename=payload.get("filename")
            if isinstance(payload.get("filename"), str)
            else None,
        )
