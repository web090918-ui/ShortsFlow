# ShortsFlow

ShortsFlow is a decision-first workflow for selecting the best short-form video candidates before rendering them. This repository currently contains the Task 01 project skeleton only.

## Structure

```text
.
├── frontend/   # Next.js App Router application
├── backend/    # FastAPI application
└── docs/       # Product and architecture documentation location
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

Environment variables use the `SHORTSFLOW_` prefix:

- `SHORTSFLOW_APP_NAME`
- `SHORTSFLOW_APP_ENV`
- `SHORTSFLOW_LOG_LEVEL`

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

Task 01 intentionally contains no Supabase, YouTube API, AI/STT, Cloud Tasks, Redis, Kafka, or Kubernetes integration.

