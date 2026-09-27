import argparse
import json
import time
from typing import Any
from urllib.parse import urljoin
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.youtube import (
    PreparedVideoSource,
    VideoSourceProvider,
    VideoSourceProviderError,
    YouTubeSourceProvider,
)


class AcquisitionProbeError(Exception):
    """A validation failure that is safe to print without exposing stream URLs."""


def _probe_stream(
    stream: dict[str, Any],
    *,
    timeout_seconds: float,
    opener: Any = urlopen,
) -> dict[str, Any]:
    headers = {str(key): str(value) for key, value in stream.get("http_headers", {}).items()}
    current_url = str(stream["url"])
    manifest_hops = 0

    for _ in range(3):
        request_headers = dict(headers)
        request_headers["Range"] = "bytes=0-65535"
        request = Request(current_url, headers=request_headers)

        try:
            with opener(request, timeout=timeout_seconds) as response:
                status_code = getattr(response, "status", response.getcode())
                content_type = response.headers.get("Content-Type", "")
                looks_like_manifest = (
                    "mpegurl" in content_type.lower()
                    or ".m3u8" in current_url.split("?", maxsplit=1)[0].lower()
                )
                sample = response.read(65536 if looks_like_manifest else 1024)
                response_url = getattr(response, "geturl", lambda: current_url)()
        except HTTPError as exc:
            raise AcquisitionProbeError(
                f"{stream.get('format_id', 'unknown')} stream returned HTTP {exc.code}."
            ) from exc
        except (TimeoutError, URLError, OSError) as exc:
            raise AcquisitionProbeError(
                f"{stream.get('format_id', 'unknown')} stream could not be read."
            ) from exc

        if status_code not in {200, 206}:
            raise AcquisitionProbeError(
                f"{stream.get('format_id', 'unknown')} stream returned HTTP {status_code}."
            )
        if not sample:
            raise AcquisitionProbeError(
                f"{stream.get('format_id', 'unknown')} stream returned no data."
            )

        is_hls_manifest = "mpegurl" in content_type.lower() or sample.startswith(b"#EXTM3U")
        if not is_hls_manifest:
            break

        manifest_hops += 1
        media_lines = [
            line.strip()
            for line in sample.decode("utf-8", errors="replace").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        if not media_lines:
            raise AcquisitionProbeError(
                f"{stream.get('format_id', 'unknown')} HLS manifest has no media URI."
            )
        current_url = urljoin(response_url, media_lines[0])
    else:
        raise AcquisitionProbeError(
            f"{stream.get('format_id', 'unknown')} HLS manifest nesting is too deep."
        )

    return {
        "format_id": stream.get("format_id"),
        "status_code": status_code,
        "content_type": content_type,
        "sample_bytes": min(len(sample), 1024),
        "manifest_hops": manifest_hops,
    }


def run_probe(
    url: str,
    *,
    timeout_seconds: float = 20,
    provider: VideoSourceProvider | None = None,
    opener: Any = urlopen,
) -> dict[str, Any]:
    started_at = time.monotonic()
    prepared: PreparedVideoSource = (provider or YouTubeSourceProvider()).prepare(url)
    streams = prepared.processing_reference["streams"]
    stream_results = {
        kind: _probe_stream(
            streams[kind], timeout_seconds=timeout_seconds, opener=opener
        )
        for kind in ("video", "audio")
    }
    youtube_metadata = prepared.metadata["youtube"]
    return {
        "ok": True,
        "video_id": youtube_metadata.get("video_id"),
        "title": youtube_metadata.get("title"),
        "duration_seconds": youtube_metadata.get("duration_seconds"),
        "elapsed_seconds": round(time.monotonic() - started_at, 3),
        "streams": stream_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate YouTube metadata and readable media streams without downloading a video."
    )
    parser.add_argument("url", help="A public YouTube video URL to validate.")
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()

    try:
        report = run_probe(args.url, timeout_seconds=args.timeout)
    except (VideoSourceProviderError, AcquisitionProbeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
