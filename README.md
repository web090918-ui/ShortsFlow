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

## Current status

Tasks 01 and 02 are complete. The application can classify a YouTube video URL or Product URL, register video upload metadata, and return a common Source response. The next task is Task 03: YouTube Source Processing.

Task 02 intentionally uses process-local in-memory Source storage. Restarting the backend clears registered Sources, and uploaded file content is not persisted yet. No remote source extraction, transcript, async job, ranking, rendering, or affiliate processing is implemented.

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

Requirements: Python 3.13 or newer.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
fastapi dev app/main.py
```

The API is available at `http://localhost:8000`; health status is exposed at `GET /health`.

Task 02 Source endpoints:

- `POST /sources` — classify and create a YouTube or Product URL Source
- `POST /sources/upload` — validate a video file and create an Upload Source from its metadata
- `GET /sources/{source_id}` — read the current Source status

Environment variables use the `SHORTSFLOW_` prefix:

- `SHORTSFLOW_APP_NAME`
- `SHORTSFLOW_APP_ENV`
- `SHORTSFLOW_LOG_LEVEL`
- `SHORTSFLOW_FRONTEND_ORIGIN`

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
