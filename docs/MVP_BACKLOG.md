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

## Task 03A — Dedicated YouTube Acquisition Worker Validation

Status: Complete — dedicated cloud VM candidate rejected

Goal: validate the Task 03 provider on a non-Vercel worker host before adding async orchestration.

- Verify metadata plus readable video/audio stream bytes with an authorized public test video.
- Require three consecutive passes on the candidate worker environment.
- Keep the validation runner independent of Cloud Tasks and transcript processing.
- Do not add cookies, proxy rotation, or a PO-token service without an explicit decision.
- See [Task 03A validation](TASK_03A_VALIDATION.md) for the executable acceptance criteria.

## Task 03B — Selected-range Acquisition Prototype

Status: Complete — external selected-range acquisition validated

Goal: validate the URL, start/end selection, asynchronous-looking status, and MP4 download interaction without implementing Task 04 infrastructure.

- Let a user select up to 60 minutes from a `READY` YouTube Source.
- Request only the selected time range as a 480p analysis proxy through the yt-dlp/FFmpeg provider path.
- Return `202`, expose polling state, and provide an MP4 download endpoint.
- Keep jobs and files process-local for this prototype; do not add Cloud Tasks, Redis, Kafka, or object storage here.
- Treat cloud-IP bot challenges and durable execution as unresolved production gates.
- Process only user-owned or otherwise authorized videos.

Validation result:

- Tunelio `/info` returned usable metadata for the authorized test source.
- Tunelio `/create` plus `start` and `end` returned a playable 480p selected-range MP4.
- The observed 60-second request produced a 59-second artifact because provider clipping is keyframe-aligned; exact final boundaries remain a Task 08 FFmpeg responsibility.
- The API key is server-only and is never included in frontend code or repository files.

## Task 03C — PO Token Provider Revalidation

Status: Complete — rejected for the tested Lightsail environment

Goal: determine whether an automatically managed PO Token Provider changes the negative Lightsail acquisition result without adding account cookies or a proxy.

- A fresh Seoul Lightsail instance loaded `bgutil:http-2.0.0` successfully.
- The forced `mweb` client detected video-bound GVS PO Token enforcement.
- YouTube returned `LOGIN_REQUIRED` from the Player API before usable formats were exposed.
- No account cookies, residential proxy, or manually copied token was used.
- Do not repeat this configuration on additional generic Lightsail instances; validate an external acquisition contract next.

## Task 04 — Async Job

Status: Complete — code and Cloud Run validation complete

Goal: execute long-running pipeline steps through Cloud Tasks and a Worker.

- Define processing job states, retry behavior, and failure reporting.
- Enqueue work through Cloud Tasks instead of holding the initiating HTTP request open.
- Add an authenticated Worker endpoint in the same backend codebase.
- Make task handling idempotent so duplicate delivery does not duplicate results.
- Keep Cloud Tasks concerns outside the business pipeline steps.
- Do not add Redis, Kafka, Kubernetes, or a microservice split.

Implementation status:

- `ProcessingJob` exposes `QUEUED -> PROCESSING -> COMPLETED | FAILED`.
- Firestore and in-memory repository adapters share one job contract.
- Cloud Tasks uses deterministic task names and an OIDC token.
- The Worker validates the token audience and service-account email.
- A processing lease and terminal-state check make duplicate delivery idempotent.
- The current Worker completes only `PIPELINE_BOOTSTRAP`; transcript work remains Task 05.
- The deployed Seoul-region path was validated with Firestore database `shortflow`,
  Cloud Tasks queue `shortsflow-processing`, and the `shortsflow-runtime` identity.
- Production validation reached `COMPLETED`, progress `100`, and
  `result.next_step=TRANSCRIPT` after one Worker attempt. An unauthenticated direct
  Worker request returned `401`.
- See [Task 04 Cloud Run deployment](TASK_04_DEPLOYMENT.md) for the deployed configuration.

## Task 05 — Transcript

Status: In progress — code complete, production provider validation pending

Goal: create a timestamped transcript from a processable video Source.

- Extract audio with FFmpeg.
- Send the audio to the selected STT provider.
- Normalize the result into a timestamped transcript.
- Persist transcript status and actionable errors.
- Keep FFmpeg execution and the STT provider behind small boundaries needed for testing.

Implementation status:

- Tunelio timestamped captions are requested first and filtered to the selected range.
- Transcript language defaults to `ko` for the Korean MVP and is carried explicitly to both caption and STT providers.
- Caption results are cached per warm backend instance to avoid duplicate paid calls.
- A missing caption track or an empty selected-caption range falls back to the 480p analysis proxy.
- FFmpeg extracts a 16 kHz mono 32 kbps MP3, which stays below the OpenAI 25 MB upload limit for the maximum 60-minute source range.
- OpenAI `whisper-1` returns segment timestamps, which are normalized to absolute source-video time.
- The normalized transcript is persisted in the Firestore processing job result and advances `next_step` to `CANDIDATE`.
- Task 05 is not complete until both the caption-first path and Whisper fallback are validated on Cloud Run.

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
- Apply the previously selected MVP caption template (`CLEAN_CAPTION`, `BOLD_HIGHLIGHT`, or `MINIMAL`).
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
