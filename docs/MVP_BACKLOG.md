# ShortsFlow MVP1 Backlog

## Delivery rule

Tasks are completed in order. The YouTube URL flow must reach preview and download before Product/Affiliate work begins. A task must not silently include work from the next task.

## Task 01 — Minimum Project Skeleton

Status: Complete

- Next.js TypeScript App Router frontend
- Minimal Home page and environment-based API URL
- FastAPI backend with health endpoint, settings, logging, exception handling, tests, and Dockerfile
- Repository documentation and development guidance

## Task 02 — Source Input Framework

Status: Complete

Goal: establish the shared input contract before implementing any provider extraction.

- Define the `Source` domain/API shape with `YOUTUBE`, `PRODUCT`, and `UPLOAD` types.
- Add a minimal source input UI for URL and file selection.
- Validate and classify supported inputs without fetching remote content.
- Define source creation and status responses.
- Add only the persistence boundary required by this task; do not assume Supabase or another vendor without an explicit decision.
- Keep provider-specific behavior out of shared source logic.

Acceptance criteria:

- A valid YouTube URL, Product URL, or video upload can be represented by the common Source contract.
- Invalid and unsupported input receives a clear error.
- Frontend and backend contracts are covered by relevant tests.
- No transcript, AI ranking, rendering, or product extraction is implemented.

## Task 03 — YouTube Source Processing

Status: Complete

Goal: turn a validated YouTube Source into video metadata and a source that downstream processing can actually consume.

- Implement the first `VideoSourceProvider` behavior for YouTube URLs.
- Acquire required video metadata.
- Produce a stable media or processing reference for later audio extraction and rendering.
- Track acquisition status and actionable errors.
- Isolate YouTube-specific parsing and API behavior from shared Source logic.
- Do not generate transcripts or candidates yet.

## Task 04 — Async Job

Status: Next

Goal: execute long-running pipeline steps through Cloud Tasks and a Worker.

- Define processing job states, retry behavior, and failure reporting.
- Enqueue work through Cloud Tasks instead of holding the initiating HTTP request open.
- Add an authenticated Worker endpoint in the same backend codebase.
- Make task handling idempotent so duplicate delivery does not duplicate results.
- Keep Cloud Tasks concerns outside the business pipeline steps.
- Do not add Redis, Kafka, Kubernetes, or a microservice split.

## Task 05 — Transcript

Goal: create a timestamped transcript from a processable video Source.

- Extract audio with FFmpeg.
- Send the audio to the selected STT provider.
- Normalize the result into a timestamped transcript.
- Persist transcript status and actionable errors.
- Keep FFmpeg execution and the STT provider behind small boundaries needed for testing.

## Task 06 — Candidate Generation

- Generate 10-15 timestamped candidates from the transcript and video context.
- Store candidate boundaries and supporting text needed for ranking and rendering.
- Ensure each candidate can stand alone as a Short.
- Do not personalize candidates with channel data.

## Task 07 — Generic AI Ranking and Top 3

- Score candidates using generic ranking criteria.
- Return the Top 3 with concise recommendation reasons.
- Use `AI Score` or `Recommended Score` in the UI.
- Do not implement Personal Virality Score.

## Task 08 — Preview and Render

- Let the user inspect the Top 3 and select one candidate.
- Render the selected candidate as a basic 9:16 Short.
- Provide a preview of the completed render.
- Track render state and failure details.
- Do not build an advanced timeline editor or advanced auto reframe.

## Task 09 — Download UX

- Provide a clear download action for the completed render.
- Handle unavailable, expired, and failed artifacts with useful UI states.
- Complete the YouTube URL to downloadable Short end-to-end acceptance path.

## Task 10 — Product/Affiliate Flow

Begin only after Task 09 is complete.

- Implement `ProductSourceProvider` for selected product URL providers.
- Extract product facts and usable images/video.
- Analyze selling points and generate three content angles.
- Generate Hook, Script, and CTA.
- Compose product media, TTS, and captions into a Short.
- Reuse render, preview, and download capabilities where appropriate.
- Do not implement affiliate conversion tracking.

## Deferred to MVP2

- Channel connection
- Channel DNA
- Personal Ranking and Personal Virality Score
- YouTube Analytics

## Deferred to MVP3

- Automatic publishing
- Published-performance collection
- Measure/Learn feedback loop
- Better recommendations based on performance

## Out of MVP1

- Instagram and TikTok
- Competitor-channel analysis and Trend Discovery
- AI Avatar and Voice Clone
- Advanced Timeline Editor and Advanced Auto Reframe
- AI B-roll
- Affiliate Conversion Tracking
- Kubernetes, Kafka, Redis, and Microservices
