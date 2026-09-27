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

Task 03A validates acquisition separately from orchestration. Vercel remains suitable for the frontend and lightweight API, but it is not the media-acquisition runtime because the tested shared egress IP receives a YouTube bot challenge. A candidate dedicated worker must pass the repository acquisition probe three consecutive times, including readable video and audio media bytes, before Task 04 begins.

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
