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

Status: Complete — Cloud Run caption and Whisper fallback paths validated on 2026-09-29

Goal: create a timestamped transcript from a processable video Source.

- Extract audio with FFmpeg.
- Send the audio to the selected STT provider.
- Normalize the result into a timestamped transcript.
- Persist transcript status and actionable errors.
- Keep FFmpeg execution and the STT provider behind small boundaries needed for testing.

Implementation status:

- Provider captions (Apify Titan since 2026-09-29; Tunelio before) are requested first and filtered to the selected range.
- Transcript language defaults to `ko` for the Korean MVP and is carried explicitly to both caption and STT providers.
- Caption results are cached per warm backend instance to avoid duplicate paid calls.
- A missing caption track or an empty selected-caption range falls back to the 480p analysis proxy.
- FFmpeg extracts a 16 kHz mono 32 kbps MP3, which stays below the OpenAI 25 MB upload limit for the maximum 60-minute source range.
- OpenAI `whisper-1` returns segment timestamps, which are normalized to absolute source-video time.
- The normalized transcript is persisted in the Firestore processing job result and advances `next_step` to `CANDIDATE`.
- Cloud Run caption-first validation completed with `provider=tunelio`, requested and returned language `ko`, 37 timestamped segments within source range 60-120 seconds, and one Worker attempt.
- OpenAI billing and its Secret Manager-backed key are configured. A direct Google Cloud Shell request using the exact latest secret completed against `whisper-1` with HTTP `200`, validating the key, billing, project access, and model access.
- A subsequent Cloud Run fallback job did not reach OpenAI because Tunelio credits were exhausted before selected-range media acquisition.
- Decision 2026-09-29: Tunelio retired; Apify Titan now provides captions and the full-source media for the Whisper fallback, with FFmpeg trimming the selected range.
- Cloud Run validation on 2026-09-29: the caption path completed with `provider=apify_titan` (3 segments, 32 seconds) and the fallback path completed with `provider=openai_whisper` (5 segments, 3 minutes 42 seconds), both within the requested 2-12 second range. See [Task 05](TASK_05_TRANSCRIPT.md).

## Task 05B — Manual-range Short

Status: Complete — Cloud Run validation passed on 2026-09-29

Goal: deliver the MVP1 promise without AI: the user enters a YouTube URL, a start time, and an end time, and downloads that range as a 1080x1920 MP4.

- Accept `youtube_url`, `start_seconds`, `end_seconds`, and the rights declaration through `POST /shorts`.
- Validate `start >= 0`, `end > start`, a 180-second maximum clip length, and the known source duration.
- Acquire the full source through `VideoAcquisitionProvider` (Apify Titan in production, yt-dlp locally). Acquisition never edits video.
- Trim and convert to 9:16 through `VideoProcessor` (FFmpeg scale + center crop, H.264/AAC).
- Store the result through `ArtifactStorage` (local disk or Cloud Storage signed URL) and expose `GET /shorts/{id}` plus a download.
- Run everything as a `SHORT_RENDER` step on the Task 04 processing job, Cloud Tasks queue, and Worker.
- Expose `queued`, `downloading`, `processing`, `uploading`, `completed`, and `failed`; store internal error codes and return friendly messages.
- Remove temporary media after every attempt.
- Do not add AI highlight detection, face tracking, automatic scene cuts, B-roll, or template-specific rendering.

Implementation status:

- Backend, frontend form with `HH:MM:SS` input, and tests are complete.
- Cloud Run jobs completed with `provider=apify_titan` and `storage=gcs`; the signed-URL download measured 1080x1920 and 10.00 seconds for a 10-second request. See [Task 05B](TASK_05B_MANUAL_SHORT.md).
- Local storage is development-only: on Cloud Run a file request can reach a different instance than the one that rendered it.

## Task 06 — Candidate Generation

Status: Complete — Cloud Run validation passed on 2026-09-29 (15 candidates from a 15-minute Korean range)

- Generate 10-15 timestamped candidates from the transcript and video context.
- Store candidate boundaries and supporting text needed for ranking and rendering.
- Ensure each candidate can stand alone as a Short.
- Do not personalize candidates with channel data.

Implementation status:

- `HeuristicCandidateGenerator` groups transcript segments into sentence/pause-bounded speech units, slides 15-60 second windows over them, prefers sentence-boundary starts, removes near-duplicates, and thins to at most 15 candidates spread across the selected range.
- Generation runs in the same Worker attempt as the transcript; the job moves to `step=CANDIDATE` and completes with `result.candidates` and `next_step=RANKING`.
- Each candidate carries absolute timestamps, the supporting transcript text, a hook line, word density, boundary flags, and surrounding pause lengths for Tasks 07 and 08.
- Deterministic, no external calls, no channel data. See [Task 06](TASK_06_CANDIDATES.md).

## Task 07 — Generic AI Ranking and Top 3

Status: Implemented — Cloud Run validation blocked: the OpenAI project has no access to `gpt-4.1-mini` (HTTP 403). Allow the model or change `SHORTSFLOW_OPENAI_RANKING_MODEL`, then rerun the production check.

- Score candidates using generic ranking criteria.
- Return the Top 3 with concise recommendation reasons.
- Use `AI Score` or `Recommended Score` in the UI.
- Do not implement Personal Virality Score.

Implementation status:

- `OpenAIRanker` scores every candidate 0-100 on hook, self-containment, complete thought, payoff, and pacing, with a Korean reason plus strengths and concerns, through Chat Completions JSON output on the existing OpenAI key.
- Ranking runs in the same Worker attempt after candidates; the job moves to `step=RANKING` and completes with `result.ranking` and `next_step=RENDER`.
- Top 3 are the best-scored candidates that do not overlap each other by more than half.
- Incomplete model output is a retryable failure; without an OpenAI key a structural development ranker keeps local runs working.
- No channel data is read. See [Task 07](TASK_07_RANKING.md).

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
