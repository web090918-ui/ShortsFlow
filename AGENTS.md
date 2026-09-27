# ShortsFlow Development Guide

## Product direction

ShortsFlow is not merely a Shorts generator. Its long-term value is learning which Shorts a creator should make and improving future recommendations. Development must still validate the simplest immediate value first.

The MVP1 promise is: provide one source and create a downloadable Short.

Supported source types are:

- `YOUTUBE`: YouTube video URL
- `PRODUCT`: affiliate or product URL
- `UPLOAD`: uploaded video file

## MVP phases

- MVP1 — Create: URL or upload to rendered Short, preview, and download
- MVP2 — Personalize: channel connection, Channel DNA, and personal ranking
- MVP3 — Learn: publish, measure, learn, and improve recommendations

Channel DNA and analytics are not MVP1 prerequisites.

## MVP1 delivery order

Do not attempt to complete the YouTube and Product flows simultaneously. Deliver work in this order:

1. Task 02 — Source Input Framework
2. Task 03 — YouTube Source processing
3. Task 03A — Validate YouTube acquisition on a dedicated worker host
4. Task 04 — Async Job with Cloud Tasks and a Worker
5. Task 05 — Transcript with FFmpeg audio extraction and STT
6. Task 06 — Generate 10-15 Clip Candidates
7. Task 07 — Generic AI Ranking and Top 3
8. Task 08 — Preview and 9:16 Short Render
9. Task 09 — Download UX
10. Task 10 — Product/Affiliate Flow

Complete the YouTube URL to downloadable Short flow end-to-end before implementing the Product/Affiliate flow.

## Product rules

- Use a common `Source` entity for `YOUTUBE`, `PRODUCT`, and `UPLOAD` inputs.
- Keep provider-specific extraction details behind small provider boundaries when they are needed.
- Use Generic AI Ranking in MVP1. Do not call it Personal Virality Score.
- Use `AI Score` or `Recommended Score` in user-facing copy.
- Prefer direct, readable code over speculative abstractions.
- Preserve a path to later phases without implementing them early.

## MVP1 exclusions

Do not implement the following unless the product scope is explicitly changed:

- Channel DNA or YouTube Analytics
- Personal Virality Score
- Automatic publishing or performance collection
- Instagram or TikTok integrations
- Competitor-channel analysis or trend discovery
- AI Avatar or Voice Clone
- Advanced timeline editing or advanced auto reframe
- AI B-roll
- Affiliate conversion tracking
- Microservices, Kubernetes, Redis, or Kafka

## Repository constraints

- Keep the repository as a simple `frontend` and `backend` application.
- Do not spread YouTube or product-site parsing logic throughout business logic.
- In Task 04, use Cloud Tasks to invoke a Worker from the same backend codebase; do not turn it into a microservice architecture.
- Add only the abstraction needed by the current task.
- Do not add external services or infrastructure before the task that requires them.
- Do not begin the next backlog task as part of the current task.

## Validation

Run the checks relevant to every implementation change:

```text
cd frontend && npm run lint
cd frontend && npm run build
cd backend && pytest
docker build -t shortsflow-backend ./backend
```
