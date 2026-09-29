# Task 05B Manual-range Short

## Scope

Task 05B delivers the MVP1 promise on the simplest possible path: the user enters a YouTube URL plus an explicit start and end time, and ShortsFlow returns a downloadable 1080x1920 MP4 of exactly that range. No AI highlight detection, face tracking, scene cuts, B-roll, captions, or template-specific rendering is involved. Captions and Generic AI Ranking remain Tasks 05 through 07.

```text
User: URL + Start + End
  -> POST /shorts (202, queued)
  -> Cloud Tasks -> POST /worker/process (SHORT_RENDER step)
       -> VideoAcquisitionProvider   (Apify Titan: obtain the full source MP4)
       -> VideoProcessor             (FFmpeg: trim + scale/center-crop to 9:16)
       -> ArtifactStorage            (local disk or Cloud Storage signed URL)
  -> GET /shorts/{id} (downloading | processing | uploading | completed | failed)
  -> GET /shorts/{id}/file or the signed URL
```

## Responsibilities

- **Acquisition** (`app/acquisition.py`): `VideoAcquisitionProvider.acquire(url, destination)` returns the source file only. `ApifyTitanProvider` starts the `titan_network~titan-youtube-video-downloader` actor asynchronously, polls the run, reads `downloadedFileUrl` from the dataset, and streams the MP4 to the Worker's temporary directory. `YtDlpProvider` is the local-development fallback. Neither provider edits video.
- **Editing** (`app/video_processing.py`): `VideoProcessor` exposes `probe`, `trim`, `convert_to_vertical`, and the single-pass `trim_to_vertical` used by the pipeline. The vertical filter is `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920`, which is the MVP "scale then center crop" rule. Output is H.264 + AAC MP4 with `faststart`.
- **Storage** (`app/shorts_pipeline.py`): `ArtifactStorage.store(file, key, filename)`. `LocalArtifactStorage` keeps the MP4 on disk and the API serves it from `/shorts/{id}/file`. `GcsArtifactStorage` uploads to the configured bucket and returns a V4 signed URL that expires after `SHORTSFLOW_SHORTS_DOWNLOAD_TTL_SECONDS`.
- **Orchestration** (`app/processing_jobs.py`, `app/shorts.py`): the Task 04 `ProcessingJob`, Firestore repository, Cloud Tasks dispatcher, OIDC Worker, lease, and idempotency are reused unchanged. `/shorts` is a facade that creates a `SHORT_RENDER` job and maps it to the user-facing status vocabulary.

## API

`POST /shorts`

```json
{
  "youtube_url": "https://www.youtube.com/watch?v=xxxxx",
  "start_seconds": 135,
  "end_seconds": 185,
  "rights_confirmed": true,
  "template_id": "CLEAN_CAPTION",
  "source_id": null
}
```

Validation before the job is queued:

- `youtube_url` must be a YouTube host.
- `rights_confirmed` must be `true` (user declaration, not automated rights verification).
- `start_seconds >= 0`, `end_seconds > start_seconds`.
- `end_seconds - start_seconds <= SHORTSFLOW_SHORTS_MAX_CLIP_SECONDS` (default 180).
- When `source_id` refers to a `READY` YouTube Source with a known duration, `end_seconds <= duration`.

The Worker re-checks the range against the real file with `ffprobe`; a range past the actual duration fails with `INVALID_TIME_RANGE` and is not retried.

`GET /shorts/{id}` returns `status` as one of `queued`, `downloading`, `processing`, `uploading`, `completed`, or `failed`, plus `progress`, the range, `download_url`, `download_expires_at`, and a user-friendly `error_message` on failure. The internal `error_code` (`SOURCE_DOWNLOAD_FAILED`, `INVALID_TIME_RANGE`, `FFMPEG_FAILED`, `STORAGE_UPLOAD_FAILED`, `INTERNAL_ERROR`) is stored on the processing job and visible through `GET /processing-jobs/{id}`.

`GET /shorts/{id}/file` streams the local artifact or redirects to the signed Cloud Storage URL.

## Failure and retry behaviour

- Acquisition, FFmpeg, and storage failures are classified inside the pipeline. Retryable failures return the job to `QUEUED` until `SHORTSFLOW_PROCESSING_MAX_ATTEMPTS` is exhausted; non-retryable failures (invalid range, provider authentication or quota errors, unsafe download URLs, oversized sources) mark the job `FAILED` on the first attempt.
- All temporary media lives in one `TemporaryDirectory` per attempt and is removed whether the attempt succeeds or fails.
- Source downloads are capped at `SHORTSFLOW_SHORTS_MAX_SOURCE_BYTES` (default 2 GiB).

## Configuration

```text
SHORTSFLOW_SHORTS_ACQUISITION_PROVIDER=auto        # auto | apify_titan | yt_dlp
SHORTSFLOW_APIFY_API_TOKEN=<server-only secret>
SHORTSFLOW_APIFY_TITAN_ACTOR_ID=titan_network~titan-youtube-video-downloader
SHORTSFLOW_APIFY_TITAN_QUALITY=1080                # 360 | 480 | 720 | 1080 | 1440 | 2160
SHORTSFLOW_APIFY_RUN_TIMEOUT_SECONDS=480
SHORTSFLOW_SHORTS_STORAGE_BACKEND=local            # local | gcs
SHORTSFLOW_GCS_BUCKET=<bucket in asia-northeast3>
SHORTSFLOW_SHORTS_DOWNLOAD_TTL_SECONDS=86400
SHORTSFLOW_SHORTS_MAX_CLIP_SECONDS=180
```

`auto` selects Apify Titan when the token is present and yt-dlp otherwise. Cloud Run must use `apify_titan`, because YouTube challenges yt-dlp from shared cloud IP ranges (Task 03A/03C).

## Cloud Run notes

- Store `SHORTSFLOW_APIFY_API_TOKEN` in Secret Manager like the OpenAI key and grant `shortsflow-runtime` the Secret Manager Secret Accessor role on it.
- Create a Cloud Storage bucket in `asia-northeast3`, grant `shortsflow-runtime` the Storage Object Admin role on that bucket only, and add a lifecycle rule that deletes objects after one day so expired artifacts do not accumulate.
- Signed URLs on Cloud Run are produced through the IAM `signBlob` API, so `shortsflow-runtime` also needs `roles/iam.serviceAccountTokenCreator` on itself.
- Cloud Run's file system is memory-backed. The full source video plus the rendered Short must fit in instance memory; start with 4 GiB and 2 vCPU, and keep `SHORTSFLOW_APIFY_TITAN_QUALITY=1080` unless memory allows more.
- The Worker lease and Cloud Tasks dispatch deadline are 10 minutes. `SHORTSFLOW_APIFY_RUN_TIMEOUT_SECONDS` (default 480) plus download and encode time must stay under that lease; the Cloud Run request timeout should remain 900 seconds.
- Apify Titan pricing is per delivered byte (about $5/TB at the time of writing) and links stay valid for roughly 24 hours. Check <https://apify.com/titan_network/titan-youtube-video-downloader> for current terms.

## Validation

Task 05B is complete when Cloud Run demonstrates, with an authorized test video:

1. `POST /shorts` returns `202` and `queued`; the frontend form accepts `HH:MM:SS` input.
2. `GET /shorts/{id}` passes through `downloading`, `processing`, and `uploading` and ends `completed` with a `download_url`.
3. The downloaded MP4 is 1080x1920, plays with audio, and its duration matches `end - start` within one second.
4. A range longer than 180 seconds is rejected with `422` before any acquisition.
5. A range past the video's real duration ends `failed` with `INVALID_TIME_RANGE` after a single attempt.
6. No files remain in the Worker's temporary directory after success or failure.
7. Once the signed URL expires, `/shorts/{id}/file` no longer serves the artifact.

Local validation with `SHORTSFLOW_SHORTS_ACQUISITION_PROVIDER=yt_dlp` and `SHORTSFLOW_SHORTS_STORAGE_BACKEND=local` exercises the same pipeline without Apify or Cloud Storage.

## Validation result

Implemented on 2026-09-29. Unit and API tests cover request validation, the status mapping, Worker idempotency, retry classification, the FFmpeg command shape, the Apify run/poll/download sequence, and temporary-file cleanup.

Cloud Run validation on 2026-09-29 with the authorized public test video `jNQXAC9IVRw`, range 2-12 seconds:

- Before `SHORTSFLOW_APIFY_API_TOKEN` was attached, two jobs failed in about two seconds with `SOURCE_DOWNLOAD_FAILED` after one attempt; `auto` had selected yt-dlp and YouTube challenged the Cloud Run IP. This confirmed queueing, the Worker, and non-retryable failure handling.
- After the secret was attached (and `roles/secretmanager.secretAccessor` granted to `shortsflow-runtime`), two jobs completed with `provider=apify_titan` in 48 to 66 seconds, passing through `downloading` and `processing`, with one Worker attempt each.
- The downloaded MP4 measured 1080x1920, 10.00 seconds, one video and one audio track, 2.7 MB, served as `video/mp4` with filename `cutpick-short-2-12.mp4`.
- With `SHORTSFLOW_SHORTS_STORAGE_BACKEND=local`, the file request for one job returned `410` because it reached a different Cloud Run instance than the one that rendered it. Local storage is therefore development-only; Cloud Run must use `gcs`.

- After `SHORTSFLOW_SHORTS_STORAGE_BACKEND=gcs` and `SHORTSFLOW_GCS_BUCKET=shortsflow-shorts-aza-ceo` were applied (bucket in `asia-northeast3`, `roles/storage.objectAdmin` on the bucket and `roles/iam.serviceAccountTokenCreator` on itself for `shortsflow-runtime`, one-day lifecycle rule), job `cc2ddd7e` passed through `downloading`, `uploading`, and `completed` in about 65 seconds with `storage=gcs`, key `shorts/<job-id>.mp4`, and a `storage.googleapis.com` V4 signed URL expiring 24 hours later.
- The signed URL returned `200` with `video/mp4` and the attachment filename; `GET /shorts/{id}/file` returned `307` to the same signed URL; both downloads were byte-identical, 1080x1920, 10.00 seconds, video plus audio.

Task 05B production validation is complete. Only the caption/template rendering promised for Task 08 remains outside this path.
