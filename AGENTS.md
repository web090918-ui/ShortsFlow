# ShortsFlow Development Guide

## Scope

ShortsFlow helps users decide which short-form videos to create. Keep changes within the task currently being implemented.

The MVP flow is:

1. Provide a video URL or upload a video.
2. Generate Shorts candidates.
3. Rank candidates with generic ranking.
4. Select the top three.
5. Render the selected result.

Channel DNA, personalized ranking, publishing, measurement, learning loops, and affiliate experiments are later work unless a task explicitly includes them.

## Architecture constraints

- Keep the repository as a simple `frontend` and `backend` application.
- Do not add microservices, Kubernetes, Redis, Kafka, or other infrastructure unless a later task explicitly requires it.
- Do not add Supabase, YouTube API, AI/STT, or Cloud Tasks integrations before their corresponding tasks.
- Prefer direct, readable code over speculative abstractions.

## Validation

Run the relevant checks before completing a change:

```text
cd frontend && npm run lint
cd frontend && npm run build
cd backend && pytest
docker build -t shortsflow-backend ./backend
```

