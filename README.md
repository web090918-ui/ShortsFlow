# ShortsFlow

ShortsFlow starts with a simple MVP1 promise: give it one source and create a downloadable Short. The first end-to-end path is YouTube URL to Short; the Product/Affiliate flow follows only after that path works.

Long term, ShortsFlow will expand from creation into channel-aware recommendations and a publish-measure-learn loop. Those later capabilities are not part of MVP1.

## MVP roadmap

- MVP1 — Create: source input, recommendation, render, preview, download
- MVP2 — Channel Connect, Channel DNA, Personal Ranking
- MVP3 — Publish, Measure, Learn, Better Recommendation

MVP1 accepts three source types:

- YouTube video URL
- Affiliate or product URL
- Video file upload

See the product, architecture, and delivery details in:

- [Product](docs/PRODUCT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [MVP backlog](docs/MVP_BACKLOG.md)
- [Competitor research](docs/COMPETITOR_RESEARCH.md)
- [Task 05 transcript](docs/TASK_05_TRANSCRIPT.md)
- [Task 05B manual-range Short](docs/TASK_05B_MANUAL_SHORT.md)
- [Task 06 candidates](docs/TASK_06_CANDIDATES.md)

## Current status

The manual-range Short path (Task 05B) is implemented: a user enters a YouTube URL plus a start and end time, `POST /shorts` queues a `SHORT_RENDER` job on the Task 04 infrastructure, the Worker acquires the source through the configured `VideoAcquisitionProvider` (Apify Titan in production, yt-dlp locally), FFmpeg trims the range and converts it to a 1080x1920 center-cropped MP4, and the artifact is stored locally or in Cloud Storage behind a signed URL. Clips are limited to 180 seconds. This path passed Cloud Run validation on 2026-09-29 with Apify Titan acquisition, Cloud Storage bucket `shortsflow-shorts-aza-ceo`, and a 1080x1920 signed-URL download; the required secrets, bucket, and IAM grants are listed in the Task 05B document.

Apify Titan is the only external YouTube provider as of 2026-09-29. Tunelio was retired after its credits ran out and its selected-range clipping proved keyframe-aligned; the module was removed and remains in git history. Titan sits behind three small boundaries so it can be swapped later: `VideoSourceProvider.prepare` (metadata mode), `fetch_subtitles` (subtitles mode, consumed by `TitanCaptionProvider`), and `VideoAcquisitionProvider.acquire` (media mode). Without `SHORTSFLOW_APIFY_API_TOKEN`, local development falls back to yt-dlp, which only works from residential IPs.

Tasks 01 through 05 and 05B are complete; both transcript paths passed Cloud Run validation on 2026-09-29. Transcript processing runs on Titan: the Worker requests Titan captions for the requested language and filters them to the selected source range. If no caption track exists or the range has no captions, and `SHORTSFLOW_OPENAI_API_KEY` is configured, the Worker acquires the full source through Titan, trims the selected range to a 16 kHz mono MP3 with FFmpeg, and sends it to OpenAI `whisper-1` for segment timestamps. In the same Worker attempt, Task 06 derives 10-15 standalone clip candidates (15-60 seconds, sentence- and pause-aligned, with supporting text) from that transcript and stores them as `result.candidates` with `next_step=RANKING`. Cloud Tasks and Firestore persist the job, transcript, and candidates. The application can also classify a YouTube video URL or Product URL, register video upload metadata, and return a common Source response; a `READY` YouTube Source exposes a start/end range selector that prepares a 480p analysis MP4 by acquiring the source through Titan and trimming with FFmpeg. Ranking, caption rendering, and affiliate processing are not implemented.

Source storage also remains process-local and in-memory. Restarting the backend clears registered Sources, and uploaded file content is not persisted yet. `POST /sources?prepare=true` keeps YouTube creation and preparation in one request for the current demo.

YouTube can reject metadata or selected-range extraction requests from shared cloud IP ranges with a bot challenge. The provider reports this as an actionable Source failure; the project does not embed account cookies, proxies, or a separate token service as a workaround. Before a range job can be created, both the UI and API require the user to confirm that they own the source video or have the permissions needed to edit and use it. This declaration is not automated rights verification or a substitute for platform compliance.

The Task 03A probe validates actual media bytes, not metadata alone:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.acquisition_probe "https://www.youtube.com/watch?v=VIDEO_ID"
```

The local environment passed three consecutive probes on 2026-09-27. AWS Lightsail workers in Seoul failed with the same YouTube bot challenge as Vercel, proving that moving the provider to a generic cloud VM is not sufficient. A fresh instance was also tested with the automatically managed `bgutil:http-2.0.0` PO Token Provider and forced `mweb`; the Player API still returned `LOGIN_REQUIRED` before formats were available. The external selected-range contract has now passed one manual end-to-end test. Repeated multi-video web validation remains required before production acceptance. See [Task 03A validation](docs/TASK_03A_VALIDATION.md) and the sanitized [competitor research](docs/COMPETITOR_RESEARCH.md).

## Structure

```text
.
|-- frontend/   # Next.js App Router application
|-- backend/    # FastAPI application
`-- docs/       # Product, architecture, and backlog documentation
```

## Frontend

Requirements: Node.js 20.9 or newer and npm.

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

The application is available at `http://localhost:3000`. Set `NEXT_PUBLIC_API_URL` in `.env.local` to the backend base URL.

## Backend

Requirements: Python 3.13 or newer. FFmpeg is also required for selected-range acquisition and is installed by the backend Dockerfile.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
fastapi dev app/main.py
```

The API is available at `http://localhost:8000`; health status is exposed at `GET /health`.

Source endpoints:

- `POST /sources` — classify and create a YouTube or Product URL Source
- `POST /sources?prepare=true` — create and synchronously prepare a YouTube Source for Task 03
- `POST /sources/upload` — validate a video file and create an Upload Source from its metadata
- `GET /sources/{source_id}` — read the current Source status
- `POST /sources/{source_id}/prepare` — prepare an existing YouTube Source
- `POST /sources/{source_id}/downloads` — enqueue acquisition of one selected range (maximum 60 minutes)
- `GET /downloads/{download_id}` — poll the selected-range job
- `GET /downloads/{download_id}/file` — download the prepared MP4
- `POST /processing-jobs` — create and enqueue a transcript processing job
- `GET /processing-jobs/{job_id}` — read durable processing state
- `POST /worker/process` — authenticated Cloud Tasks Worker target
- `POST /shorts` — queue a manual-range Short (YouTube URL + start/end, maximum 180 seconds)
- `GET /shorts/{job_id}` — read `queued | downloading | processing | uploading | completed | failed`
- `GET /shorts/{job_id}/file` — download the rendered 9:16 MP4 or redirect to its signed URL

Environment variables use the `SHORTSFLOW_` prefix:

- `SHORTSFLOW_APP_NAME`
- `SHORTSFLOW_APP_ENV`
- `SHORTSFLOW_LOG_LEVEL`
- `SHORTSFLOW_FRONTEND_ORIGIN`
- `SHORTSFLOW_OPENAI_API_KEY` — optional server-side secret; enables Whisper fallback when captions are unavailable
- `SHORTSFLOW_OPENAI_STT_MODEL` — defaults to `whisper-1` for segment timestamps
- `SHORTSFLOW_APIFY_API_TOKEN` — server-side secret; enables Apify Titan for metadata, captions, and media (required in production)
- `SHORTSFLOW_SHORTS_ACQUISITION_PROVIDER` — `auto` (default), `apify_titan`, or `yt_dlp`
- `SHORTSFLOW_SHORTS_STORAGE_BACKEND` — `local` (default) or `gcs` with `SHORTSFLOW_GCS_BUCKET`
- `SHORTSFLOW_SHORTS_MAX_CLIP_SECONDS` — defaults to `180`

The remaining Short settings are listed in [Task 05B](docs/TASK_05B_MANUAL_SHORT.md).

Task 04 Cloud Run, Firestore, Cloud Tasks, and Worker environment settings are documented in [Task 04 deployment](docs/TASK_04_DEPLOYMENT.md). Local defaults do not require Google Cloud credentials.

Current deployed entry points are `https://www.cutpick.com` for the frontend and `https://shortflow-268642207702.asia-northeast3.run.app` for the Cloud Run backend. Secret values are stored outside the repository.

## Validation

```powershell
cd frontend
npm run lint
npm run build

cd ..\backend
pytest

cd ..
docker build -t shortsflow-backend ./backend
```
