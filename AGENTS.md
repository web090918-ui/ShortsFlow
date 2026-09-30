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
4. Task 03B — Validate selected-range acquisition as a 480p analysis proxy
5. Task 03C — Revalidate Lightsail with an automatic PO Token Provider
6. Task 04 — Async Job with Cloud Tasks and a Worker
7. Task 05 — Transcript with FFmpeg audio extraction and STT
8. Task 06 — Generate 10-15 Clip Candidates
9. Task 07 — Generic AI Ranking and Top 3
10. Task 08 — Preview and 9:16 Short Render
11. Task 09 — Download UX
12. Task 10 — Product/Affiliate Flow

Complete the YouTube URL to downloadable Short flow end-to-end before implementing the Product/Affiliate flow.

Task 11 — Upload Source Processing was added after Task 10 so `UPLOAD` Sources run the same range → Top 3 → render → download flow. Task 12 — Publish to YouTube was requested by the product owner on 2026-09-30 and, once started, supersedes the "automatic publishing" exclusion below for a manual, user-triggered upload of a finished Short to the creator's own connected channel only.

Task 05B — Manual-range Short (user-entered start/end to 9:16 MP4) was added after Task 05 to reach the downloadable-Short promise without AI. It reuses the Task 04 job infrastructure and must keep acquisition (`VideoAcquisitionProvider`), editing (`VideoProcessor`), and storage (`ArtifactStorage`) behind their small boundaries so providers can be swapped.

## Product rules

- Use a common `Source` entity for `YOUTUBE`, `PRODUCT`, and `UPLOAD` inputs.
- Keep provider-specific extraction details behind small provider boundaries when they are needed.
- Use Generic AI Ranking in MVP1. Do not call it Personal Virality Score.
- Use `AI Score` or `Recommended Score` in user-facing copy.
- Require an affirmative source-rights declaration in both the UI and API before YouTube media acquisition. Treat it as a user declaration, not automated rights verification or a substitute for platform compliance.
- Use the selected range as a 480p analysis proxy. Reacquire only the final selected candidate at output quality when rendering is implemented.
- In the manual-range Short flow, the acquisition provider only obtains the source file; FFmpeg owns trimming and the 9:16 conversion. Never let a download provider edit video.
- Apify Titan is the only external YouTube provider (metadata, captions, media) as of 2026-09-29. Tunelio was retired and must not be re-added without an explicit decision. Keep every Titan call behind the existing boundaries in `app/acquisition.py` so the provider can change later.
- Carry one of the three MVP render preferences (`CLEAN_CAPTION`, `BOLD_HIGHLIGHT`, or `MINIMAL`) without implementing template-specific rendering before Task 08.
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
