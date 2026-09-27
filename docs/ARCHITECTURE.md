# ShortsFlow MVP1 Architecture

## Architecture objective

MVP1 uses a simple frontend/backend repository and supports the `source -> processing -> candidate -> render -> download` lifecycle. The architecture should keep input types consistent without introducing infrastructure or abstractions that the current task does not need.

```text
Next.js frontend
    |
    v
FastAPI backend
    |
    +-- Source lifecycle
    +-- Processing pipeline
    +-- Candidate ranking
    `-- Render lifecycle
```

This is not a microservice architecture. The Task 04 Worker is an async execution role in the same backend codebase, not an independently modeled product service.

## Common Source entity

Every input begins as a common Source.

```text
Source
- id
- user_id
- type: YOUTUBE | PRODUCT | UPLOAD
- url
- status
- metadata
- created_at
- updated_at
```

`url` may be absent for an uploaded file when the eventual storage model uses another reference. `metadata` holds source-specific facts, but stable business fields should not be hidden there merely for convenience. Exact persistence types, identifiers, and status values are defined by the implementation task that introduces storage.

Task 02 provides a `SourceRepository` boundary with an in-memory adapter. It exists to validate the Source contract, not as production persistence: data is cleared when the backend process restarts. Upload Source creation records validated file metadata but does not retain file content. Persistent records and media storage must be selected by the task that first requires processable media.

Task 03 adds `CREATED -> PREPARING -> READY | FAILED` for YouTube acquisition. During this task, `POST /sources?prepare=true` can create and prepare a YouTube Source in one request. This keeps the deployed serverless demo functional while storage remains process-local; Task 04 will replace the synchronous execution path with an async job rather than extending it further.

Task 03A validates acquisition separately from orchestration. Vercel remains suitable for the frontend and lightweight API, but it is not the direct yt-dlp media-acquisition runtime because the tested shared egress IP receives a YouTube bot challenge. A dedicated AWS Lightsail VM received the same challenge, so moving yt-dlp to a generic cloud VM is not sufficient.

Task 03B supports Tunelio as the selected-range acquisition adapter when `SHORTSFLOW_TUNELIO_API_KEY` is configured. The API key remains server-side. Source preparation calls `/info`, and range preparation calls `/create` for 480p then adds the selected `start` and `end` parameters to the returned signed tunnel URL. Media bytes flow from the provider to the browser rather than through Vercel. Without the key, local development retains the existing yt-dlp/FFmpeg prototype.

To control provider cost without adding MVP-excluded infrastructure, ready Source metadata is cached for six hours in the browser session and in each warm backend process. The base `/create` signed URL is cached by video and quality until five minutes before expiry; different ranges are derived from that URL without another paid call. The browser also reuses the active signed URL when the user changes the range or template. Failed responses are never cached. These are best-effort caches, not durable persistence, and intentionally do not introduce Redis or another service.

### Selected-range acquisition prototype

The current prototype lets a user choose a start and end time after a YouTube Source reaches `READY`. The frontend follows a job-shaped network flow similar to the behavior observed during competitor research:

```text
POST /sources/{source_id}/downloads -> 202
GET  /downloads/{download_id}       -> poll QUEUED | DOWNLOADING | READY | FAILED
GET  /downloads/{download_id}/file  -> selected MP4
```

The provider passes the requested time range to yt-dlp and FFmpeg instead of intentionally downloading the complete source first. It caps this analysis artifact at 480p to reduce transfer, storage, and decoding cost. Exact upstream byte usage still depends on the YouTube delivery format and CDN seek behavior, so this is not a guarantee that only the final MP4 bytes are transferred.

The 480p artifact is an analysis proxy, not the final render source. When rendering is implemented, ShortsFlow should reacquire only the selected 30-60 second candidate at the output-quality resolution. This avoids downloading a long source at high resolution while preventing an aggressively cropped 9:16 result from being upscaled from 480p.

The prototype also carries one of three stable template identifiers with the job: `CLEAN_CAPTION`, `BOLD_HIGHLIGHT`, or `MINIMAL`. This is a render preference only; Task 03B does not render captions. Task 08 will interpret the identifier, so acquisition code must not contain template-specific rendering behavior.

The local yt-dlp implementation deliberately uses FastAPI `BackgroundTasks`, an in-memory job repository, and local temporary files. The Tunelio path instead returns a ready signed URL in the initiating request because that provider has no job queue. The frontend still understands the job-shaped response so Task 04 can replace in-memory processing state without changing the interaction. A stateless URL fallback permits the second request to succeed if a Vercel invocation no longer has the in-memory Source. Both the frontend and API require an affirmative source-rights declaration before starting acquisition; this is not automated rights verification or a substitute for platform compliance.

## Provider boundaries

Site-specific acquisition logic must not be scattered through application business logic. Introduce small boundaries when the corresponding source is implemented, for example:

```text
VideoSourceProvider
- validate source
- fetch video information
- acquire transcript or media reference

ProductSourceProvider
- validate source
- extract product information and media
```

These are conceptual responsibilities, not a requirement for a deep class hierarchy. MVP1 should have only the provider interface and implementations needed by the active task.

The Task 03 YouTube provider resolves public video metadata and selects usable video and audio formats. Public API metadata contains format identifiers and codecs, while direct stream URLs and request headers remain in an internal processing reference. Since provider stream URLs can expire, the reference also retains the canonical video ID and page URL so a later worker can resolve fresh streams. It is a regenerable processing reference, not a permanent media artifact.

## Processing pipelines

### Video pipeline

```text
YOUTUBE or UPLOAD Source
-> video metadata/media acquisition
-> transcript
-> 10-15 clip candidates
-> Generic AI Ranking
-> Top 3
-> selected candidate
-> 9:16 render
-> preview artifact
-> downloadable artifact
```

### Product pipeline

```text
PRODUCT Source
-> product data/media extraction
-> selling points
-> 3 content angles
-> selected/generated Hook + Script + CTA
-> TTS + Caption + product media composition
-> render
-> preview artifact
-> downloadable artifact
```

The two pipelines share Source, processing status, render outcome, preview, and download concepts. They should not be forced into one identical processing implementation where their domain steps differ.

## Async processing

Transcript, candidate generation, ranking, and rendering can be long-running. API boundaries should therefore support work that progresses through explicit states instead of holding a request open indefinitely.

Task 04 uses Cloud Tasks and a Worker:

```text
FastAPI request
-> create/update processing job
-> enqueue Cloud Task
-> Worker endpoint
-> execute the current pipeline step
-> persist success or failure state
```

The Worker should be implemented from the same backend codebase and expose only the authenticated task-processing entrypoint needed by Cloud Tasks. Job handling must account for retries and idempotency because a task can be delivered more than once.

Cloud Tasks is an execution adapter. Business pipeline steps must not contain Cloud Tasks API calls directly. MVP1 does not add Redis, Kafka, Kubernetes, or a broader microservice split.

The Task 04 implementation runs the public API and authenticated Worker route from the same FastAPI image on Cloud Run. Firestore supplies durable `ProcessingJob` state. Cloud Tasks sends a Google-signed OIDC token, and the application verifies its audience and service-account email before accepting `/worker/process`. A ten-minute processing lease plus terminal-state checks make duplicate delivery idempotent. The initial `PIPELINE_BOOTSTRAP` step only validates dispatch and records `next_step=TRANSCRIPT`; it does not implement Task 05 early.

Local development defaults to an in-memory repository and FastAPI background dispatch. Production selects Firestore, Cloud Tasks, and Google OIDC through environment settings. Cloud Run Application Default Credentials are used; no service-account JSON key is stored in the repository or container.

## Transcript processing

Task 05 keeps transcript acquisition behind small caption, media acquisition, audio extraction, and STT boundaries. For a YouTube job, the Worker first requests Tunelio timestamped captions and filters them to the user-selected source range. This avoids downloading media and calling STT when usable captions already exist.

Only when the video has no caption track, or the selected range contains no caption segments, does the Worker use the fallback path:

```text
Tunelio 480p selected-range URL
-> temporary MP4 on Cloud Run
-> FFmpeg 16 kHz mono 32 kbps MP3
-> OpenAI whisper-1 verbose JSON with segment timestamps
-> absolute source-video timestamps
-> Firestore ProcessingJob.result.transcript
```

The fallback uses `whisper-1` because Task 05 requires segment timestamps. Temporary media and audio live only inside a per-job temporary directory and are deleted when processing ends. No media object storage, candidate generation, ranking, or rendering is introduced in this task. Provider authentication and credit errors remain visible job failures; only transcript absence triggers the fallback.

## Ranking boundary

Ranking accepts generic candidate content and returns scores and explanations sufficient to select the Top 3. MVP1 ranking is channel-independent and evaluates general qualities such as hook strength, completeness, density, curiosity, duration suitability, and standalone understandability.

Channel-specific inputs do not belong in this contract until MVP2.

## Evolution path

- MVP1 adds creation entities and pipelines.
- MVP2 may add channel identity, Channel DNA, and a personal ranking strategy alongside Generic AI Ranking.
- MVP3 may add publishing and performance feedback without replacing the Source and candidate history created in MVP1.

This evolution path is a compatibility goal, not permission to implement MVP2 or MVP3 fields and services during MVP1.

## Explicit non-goals

MVP1 architecture contains no microservices, Kubernetes, Kafka, Redis, social publishing integrations, analytics ingestion, Channel DNA, advanced editor, AI Avatar, Voice Clone, AI B-roll, or affiliate conversion tracking.
