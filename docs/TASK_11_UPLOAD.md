# Task 11 Upload Source Processing

## Scope

Task 11 makes the `UPLOAD` Source type a first-class input for the MVP1 flow: a creator uploads a video file, selects a range, receives the AI Score Top 3, and renders a captioned Short, exactly as with a YouTube URL. Before this task `POST /sources/upload` only recorded the file name and size and the bytes were discarded.

```text
browser: read duration with <video> -> POST /sources/upload (JSON)
  -> API registers the Source and returns an upload target
browser: PUT the file straight to the signed Cloud Storage URL (or to the API locally)
  -> POST /sources/{id}/uploaded -> API confirms the object exists -> READY
POST /processing-jobs { source_id, start, end, rights_confirmed }   (no source_url)
  -> job source_url = upload://uploads/{id}.mp4
  -> Worker: captions skipped -> Whisper transcript -> candidates -> AI ranking
POST /shorts { processing_job_id, candidate_id } -> UploadAcquirer fetches the file
  -> FFmpeg trim + 9:16 + captions -> preview / download (Tasks 08-09 unchanged)
```

## Design

- **Bytes never cross Cloud Run.** The API returns a V4 signed `PUT` URL for `uploads/{source_id}.mp4` in the artifact bucket; the browser uploads directly, which avoids the 32 MiB request limit and keeps instances free. `LocalArtifactStorage` returns no URL, so local development falls back to `PUT /sources/{id}/content`, which streams into the storage root.
- **Duration comes from the browser.** The `<video>` element reads the metadata before upload and the API stores it in `metadata.upload.duration_seconds`, so the range picker works without a server-side probe. If the browser cannot read it the value is `null` and the picker waits for a manual range.
- **One acquisition boundary.** `RoutingAcquirer` sends `upload://` URLs to `UploadAcquirer`, which copies the object from `ArtifactStorage` (`fetch_to`), and everything else to the cached Titan acquirer. The transcript step skips the caption provider for uploads and goes straight to Whisper.
- **Sources persist.** `SourceRepository` gained a Firestore adapter (collection `sources`) selected by `SHORTSFLOW_JOB_REPOSITORY_BACKEND`, so the registration, confirmation, and job creation may land on different Cloud Run instances.
- **Retention.** Uploads share the bucket's one-day lifecycle rule; an upload that is no longer present fails acquisition with "파일을 다시 업로드해 주세요" and is not retried.

## API

- `POST /sources/upload` body `{filename, content_type, size_bytes, duration_seconds}` → `201` Source plus `upload: {mode: "signed_put", url, headers}` or `{mode: "direct", url}`.
- `PUT /sources/{id}/content` (local mode) → stores the body and marks the Source `READY`.
- `POST /sources/{id}/uploaded` → `READY` when the object exists, `409` otherwise.
- `POST /processing-jobs` accepts an upload Source without `source_url`; `422` if the Source is not a `READY` upload.

## Cloud Run and bucket setup

The browser PUTs to `storage.googleapis.com`, so the bucket needs CORS for the site origin:

```json
[{"origin": ["https://www.cutpick.com", "https://cutpick.com", "http://localhost:3000"],
  "method": ["PUT", "GET", "HEAD"],
  "responseHeader": ["Content-Type", "Content-Length", "Content-Disposition"],
  "maxAgeSeconds": 3600}]
```

```bash
gcloud storage buckets update gs://shortsflow-shorts-aza-ceo --cors-file=cors.json
```

`shortsflow-runtime` already has object admin on the bucket and token-creator on itself (needed to sign the PUT URL), and Firestore access for the new `sources` collection. The upload size limit is `SHORTSFLOW_SHORTS_MAX_SOURCE_BYTES` (2 GiB by default).

## Validation

1. Unit tests cover registration targets, the local direct upload, confirmation before and after the object exists, `UploadAcquirer` and `RoutingAcquirer`, the caption skip for uploads, and a processing job created from an upload that completes through the stubbed transcript.
2. On Cloud Run: register, PUT a real MP4 to the signed URL, confirm `READY`, run the analysis job to `RENDER` with `provider=openai_whisper`, render the Top 1 candidate, and download a 1080x1920 MP4.

## Validation result

Implemented on 2026-09-30 (backend 141 tests, frontend 18 tests).

Cloud Run check 2 passed on 2026-09-30 with a 34.2 MB, 59-second Korean MP4 (the Short rendered earlier that day):

- `POST /sources/upload` returned `upload.mode=signed_put`; the PUT to the signed Cloud Storage URL completed in about a second with `200`.
- `POST /sources/{id}/uploaded` marked the Source `READY` with `media.provider=upload` and the browser-supplied duration 59.45 s. (A raw `curl -X POST` without a body is answered `411` by Google's front end before reaching Cloud Run; browsers always send `Content-Length: 0`, and the check used `-d ''`.)
- `POST /processing-jobs` without `source_url` created job `cfb321f0`, which completed in 13 seconds with `transcript.provider=openai_whisper`, 24 Korean segments, one candidate for the 59-second range, and `ranking=openai:gpt-4.1-mini` (AI Score 65).
- `POST /shorts` for that candidate created render `93bc26aa`, which completed in 1 minute 35 seconds with 24 captions, `artifact_state=ready`, and a downloadable 1080x1920, 59.0-second MP4; the 5-second frame showed the burned captions over the uploaded footage.

Task 11 is complete. Browser uploads on www.cutpick.com additionally require the bucket CORS rule above.
