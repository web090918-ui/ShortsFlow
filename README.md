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

Continuing from another machine? Start with the [handoff notes](docs/HANDOFF.md).

See the product, architecture, and delivery details in:

- [Product](docs/PRODUCT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [MVP backlog](docs/MVP_BACKLOG.md)
- [Competitor research](docs/COMPETITOR_RESEARCH.md)
- [Task 05 transcript](docs/TASK_05_TRANSCRIPT.md)
- [Task 05B manual-range Short](docs/TASK_05B_MANUAL_SHORT.md)
- [Task 06 candidates](docs/TASK_06_CANDIDATES.md)
- [Task 07 ranking](docs/TASK_07_RANKING.md)
- [Task 08 preview and render](docs/TASK_08_RENDER.md)
- [Task 09 download UX](docs/TASK_09_DOWNLOAD.md)
- [Task 11 upload sources](docs/TASK_11_UPLOAD.md)

## Current status

The manual-range Short path (Task 05B) is implemented: a user enters a YouTube URL plus a start and end time, `POST /shorts` queues a `SHORT_RENDER` job on the Task 04 infrastructure, the Worker acquires the source through the configured `VideoAcquisitionProvider` (Apify Titan in production, yt-dlp locally), FFmpeg trims the range and converts it to a 1080x1920 center-cropped MP4, and the artifact is stored locally or in Cloud Storage behind a signed URL. Clips are limited to 180 seconds. This path passed Cloud Run validation on 2026-09-29 with Apify Titan acquisition, Cloud Storage bucket `shortsflow-shorts-aza-ceo`, and a 1080x1920 signed-URL download; the required secrets, bucket, and IAM grants are listed in the Task 05B document.

Apify Titan is the only external YouTube provider as of 2026-09-29. Tunelio was retired after its credits ran out and its selected-range clipping proved keyframe-aligned; the module was removed and remains in git history. Titan sits behind three small boundaries so it can be swapped later: `VideoSourceProvider.prepare` (metadata mode), `fetch_subtitles` (subtitles mode, consumed by `TitanCaptionProvider`), and `VideoAcquisitionProvider.acquire` (media mode). Without `SHORTSFLOW_APIFY_API_TOKEN`, local development falls back to yt-dlp, which only works from residential IPs.

Tasks 01 through 09 and 05B are complete: the MVP1 YouTube path is delivered end to end and validated on Cloud Run (2026-09-29 and 2026-09-30). Task 11 makes uploaded files a first-class input for the same flow (direct-to-storage upload, Whisper transcript, Top 3, render) and passed its Cloud Run check the same day. Sources are stored in Firestore on Cloud Run. The site has three pages: `/` introduces the product and offers two entry cards; `/video` is the four-step video wizard (YouTube URL or upload → range and template → AI Score Top 3 or "이 구간 그대로 만들기" for ranges up to 180 seconds → preview and download); `/affiliate` is the affiliate wizard (Coupang Partners link → product facts and three angles → template, CTA link, disclosure consent → narrated product Short), with Agoda and Trip.com listed as planned. Task 10 (Product/Affiliate flow) is implemented for Coupang Partners links: the Partners URL is parsed into product facts, OpenAI proposes three content angles, OpenAI TTS narrates the chosen script, and FFmpeg composes a captioned 1080x1920 Short with the Partners disclosure; its Cloud Run validation is pending. Media acquisition is cached per video (`source_media` in Firestore) and resumable: when Titan needs longer than 90 seconds the job is re-queued and re-delivered every minute by a scheduled Cloud Tasks task rather than holding a Worker instance. The OpenAI key is organization-scoped and targets project `proj_InkVn5EtOT2q8LKO2v8bFE9X` through `SHORTSFLOW_OPENAI_PROJECT`. Transcript processing runs on Titan: the Worker requests Titan captions for the requested language and filters them to the selected source range. If no caption track exists or the range has no captions, and `SHORTSFLOW_OPENAI_API_KEY` is configured, the Worker acquires the full source through Titan, trims the selected range to a 16 kHz mono MP3 with FFmpeg, and sends it to OpenAI `whisper-1` for segment timestamps. In the same Worker attempt, Task 06 derives 10-15 standalone clip candidates (15-60 seconds, sentence- and pause-aligned, with supporting text) from that transcript, and Task 07 scores them with generic AI criteria (hook, self-containment, complete thought, payoff, pacing) through OpenAI, storing every candidate's `AI Score` and reason plus a time-distinct Top 3 as `result.ranking` with `next_step=RENDER`. Cloud Tasks and Firestore persist the job, transcript, candidates, and ranking. The application can also classify a YouTube video URL or Product URL, register video upload metadata, and return a common Source response; a `READY` YouTube Source exposes a start/end range selector that prepares a 480p analysis MP4 by acquiring the source through Titan and trimming with FFmpeg. Task 08 lets the user pick one of the Top 3 in the browser; `POST /shorts` with `processing_job_id` and `candidate_id` renders that candidate through the same pipeline with the chosen caption template burned in (ASS via libass, NanumGothic) and returns an inline `preview_url` next to the `download_url`. Task 09 adds `artifact_state` so expired links and removed files show a "다시 만들기" action instead of a dead link, and failures offer "다시 시도". Affiliate processing (Task 10) is not implemented.

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

Requirements: Python 3.13 or newer. FFmpeg (with libass) and a Korean font are required for rendering; the backend Dockerfile installs `ffmpeg`, `fonts-nanum`, and `fontconfig`.

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
- `POST /sources/upload` — register an upload (JSON metadata and duration) and receive a signed PUT URL or a direct upload target
- `PUT /sources/{source_id}/content` — local-development upload target; stores the file and marks the Source `READY`
- `POST /sources/{source_id}/uploaded` — confirm the uploaded object exists and mark the Source `READY`
- `GET /sources/{source_id}` — read the current Source status
- `POST /sources/{source_id}/prepare` — prepare an existing YouTube Source
- `POST /sources/{source_id}/downloads` — enqueue acquisition of one selected range (maximum 60 minutes)
- `GET /downloads/{download_id}` — poll the selected-range job
- `GET /downloads/{download_id}/file` — download the prepared MP4
- `POST /processing-jobs` — create and enqueue a transcript, candidate, and ranking job for a YouTube URL or a `READY` upload Source
- `GET /processing-jobs/{job_id}` — read durable processing state
- `POST /worker/process` — authenticated Cloud Tasks Worker target
- `POST /shorts` — queue a Short from a manual range (YouTube URL or upload `source_id` + start/end, maximum 180 seconds) or from a ranked candidate (`processing_job_id` + `candidate_id`, captions burned in)
- `GET /shorts/{job_id}` — read `queued | downloading | processing | uploading | completed | failed`, `artifact_state` (`pending | ready | expired | unavailable | failed`), `preview_url`, and `download_url`
- `GET /shorts/{job_id}/file` — download the rendered 9:16 MP4 (`?inline=true` for playback) or redirect to its signed URL
- `POST /sources/{source_id}/product-content` — selling points and three content angles for a READY product Source
- `POST /shorts/product` — render a narrated product Short from a product Source and one angle
- `GET /auth/google/start`, `GET /auth/google/callback`, `GET /auth/status`, `GET /auth/me`, `POST /auth/logout` — Google sign-in and session (Task 12A)
- `GET /me/jobs` — the signed-in account's analyses and Shorts, newest first
- `GET /me/credits` — balance, prices, and the credit ledger (1 credit = 1 source minute analysed; see [Credits and pricing](docs/CREDITS_PRICING.md))

Environment variables use the `SHORTSFLOW_` prefix:

- `SHORTSFLOW_APP_NAME`
- `SHORTSFLOW_APP_ENV`
- `SHORTSFLOW_LOG_LEVEL`
- `SHORTSFLOW_FRONTEND_ORIGIN`
- `SHORTSFLOW_OPENAI_API_KEY` — optional server-side secret; enables Whisper fallback when captions are unavailable
- `SHORTSFLOW_OPENAI_STT_MODEL` — defaults to `whisper-1` for segment timestamps
- `SHORTSFLOW_OPENAI_RANKING_MODEL` — defaults to `gpt-4.1-mini` for the generic AI Score
- `SHORTSFLOW_OPENAI_PROJECT` — optional OpenAI project id for organization-scoped keys
- `SHORTSFLOW_PROCESSING_LEASE_SECONDS` — Worker lease and Cloud Tasks deadline, default `600`; raise with the Titan run timeout and Cloud Run `--timeout` for long sources
- `SHORTSFLOW_APIFY_API_TOKEN` — server-side secret; enables Apify Titan for metadata, captions, and media (required in production)
- `SHORTSFLOW_SHORTS_ACQUISITION_PROVIDER` — `auto` (default), `apify_titan`, or `yt_dlp`
- `SHORTSFLOW_SHORTS_STORAGE_BACKEND` — `local` (default) or `gcs` with `SHORTSFLOW_GCS_BUCKET`
- `SHORTSFLOW_SHORTS_MAX_CLIP_SECONDS` — defaults to `180`

The remaining Short settings are listed in [Task 05B](docs/TASK_05B_MANUAL_SHORT.md).

Task 04 Cloud Run, Firestore, Cloud Tasks, and Worker environment settings are documented in [Task 04 deployment](docs/TASK_04_DEPLOYMENT.md). Local defaults do not require Google Cloud credentials.

Current deployed entry points are `https://www.cutpick.com` for the frontend and `https://shortflow-268642207702.asia-northeast3.run.app` for the Cloud Run backend. Secret values are stored outside the repository.

Since Task 12A the frontend calls the API through a same-origin `/api/*` rewrite (see `frontend/next.config.ts`), so the Vercel project needs `API_PROXY_TARGET=https://shortflow-268642207702.asia-northeast3.run.app` and a redeploy. Production builds always use `/api`; `NEXT_PUBLIC_API_URL` is honoured only by tests, because a leftover absolute value made the deployed site call Cloud Run directly and drop the session cookie on 2026-10-01. Before this change the deployed bundle pointed at the retired Vercel backend `shortsflow-api.vercel.app` (yt-dlp, no Titan), which produced "YouTube가 현재 서버 요청을 제한했습니다" for every YouTube URL even though Cloud Run worked. Cloud Run's `SHORTSFLOW_FRONTEND_ORIGIN` still allows `https://www.cutpick.com` for any direct calls.

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
