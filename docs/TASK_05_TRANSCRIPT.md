# Task 05 Transcript

## Scope

Task 05 produces a timestamped transcript for the user-selected YouTube source range. It does not generate clip candidates, rank content, or render video.

The production order is:

1. Request timestamped captions from the provider (Apify Titan subtitles mode, `json3`).
2. Filter captions to the selected source range.
3. If captions are unavailable for that range, acquire the full source through the provider and trim the selected range to a temporary MP3 with FFmpeg.
4. Send the MP3 to OpenAI `whisper-1` with segment timestamps.
5. Normalize timestamps to the original source-video timeline and persist the result in Firestore.

`POST /processing-jobs` accepts `transcript_language` as an ISO-style language code. The Korean MVP defaults to `ko`; callers should send another code when the source language is known. The same hint is passed to both the caption provider and Whisper so a provider default does not silently select an unrelated translated caption track.

Provider history: Tunelio was the caption and range provider until 2026-09-29, when it was retired in favour of Apify Titan (see [Architecture](ARCHITECTURE.md), "Provider decision"). Titan subtitles cost about $0.002 per item and media is billed per delivered byte; see <https://apify.com/titan_network/titan-youtube-video-downloader>.

OpenAI accepts transcription files up to 25 MB and requires `whisper-1` for segment or word timestamp granularities. The fallback MP3 uses mono 16 kHz audio at 32 kbps so the maximum 60-minute selection remains below that upload limit. See <https://developers.openai.com/api/docs/guides/speech-to-text>.

## Cloud Run secrets

Configure these values as secrets or secret-backed environment variables. Never commit their values.

```text
SHORTSFLOW_APIFY_API_TOKEN=<server-only key>
SHORTSFLOW_OPENAI_API_KEY=<server-only key>
SHORTSFLOW_OPENAI_STT_MODEL=whisper-1
```

The Apify token is required for Task 05. The OpenAI key is optional only when every processed range has usable captions; without it, a captionless range fails with an actionable error instead of silently skipping transcript generation.

## Persisted result

A completed `ProcessingJob` stores:

```text
result.next_step = CANDIDATE
result.transcript.provider = apify_titan | openai_whisper   (older jobs: tunelio)
result.transcript.language
result.transcript.is_generated
result.transcript.source_start_seconds
result.transcript.source_end_seconds
result.transcript.segments[] = { start_seconds, end_seconds, text }
result.transcript.full_text
```

Segment timestamps are absolute positions in the original source video, not positions relative to the downloaded analysis clip.

## Validation

Task 05 is complete when Cloud Run demonstrates both paths with authorized test sources:

1. A source range with captions completes with `provider=apify_titan` without media acquisition or an OpenAI call.
2. A source range without captions acquires the source through Titan, trims the range to audio with FFmpeg, and completes with `provider=openai_whisper`.
3. Both results contain non-empty timestamped segments within the requested range.
4. `next_step` is `CANDIDATE`.
5. Provider authentication, quota, media download, FFmpeg, and STT failures persist an actionable job error.
6. Temporary media is removed after each fallback attempt.

Do not start Task 06 until these production checks pass.

## Validation result

The caption-first path passed Cloud Run validation on 2026-09-27. An authorized Korean source range from 60 to 120 seconds completed in one Worker attempt with `provider=tunelio`, requested and returned language `ko`, 37 non-empty segments, progress `100`, and `next_step=CANDIDATE`.

OpenAI billing and the Secret Manager-backed `SHORTSFLOW_OPENAI_API_KEY` are now configured. On 2026-09-28, the exact latest secret was loaded from Secret Manager in Google Cloud Shell and sent directly to the OpenAI audio transcription endpoint with a generated two-second WAV. `whisper-1` returned HTTP `200`, the transcript `Beep.`, and two seconds of usage. This validates the configured key, billing, project access, and model access without exposing the secret.

The production fallback remains unvalidated end to end. A new Cloud Run processing job attempted the captionless 965-968 second range three times but stopped before OpenAI because Tunelio reported insufficient credits while acquiring the caption or selected-range media. The earlier Cloud Run OpenAI `403` therefore cannot be retested through the complete pipeline until Tunelio credits are available and the Cloud Run revision is confirmed to reference the latest OpenAI secret version.

Task 05 remains in progress and Task 06 must not begin until a Cloud Run job completes with `provider=openai_whisper`.

On 2026-09-29 the Tunelio dependency was removed. Both the caption step and the fallback media step now run on Apify Titan, so exhausted Tunelio credits no longer block validation. The results above for `provider=tunelio` remain valid history for the caption-first logic, which is unchanged apart from the provider adapter.

Cloud Run validation on 2026-09-29 with the Titan-only revision and the authorized public test video `jNQXAC9IVRw` (19 seconds, English speech), range 2-12 seconds:

- `POST /sources?prepare=true` reached `READY` in 19 seconds through Titan metadata mode with title, duration, and channel populated and `media.provider=apify_titan`.
- Caption path (`transcript_language=en`), job `2af76b99`: `COMPLETED` in 32 seconds, one Worker attempt, `provider=apify_titan`, `language=en`, `is_generated=false`, 3 segments from 2.0 to 12.0 seconds, all inside the requested range, no media acquisition or OpenAI call.
- Fallback path (`transcript_language=ko`, no Korean track), job `cb1ed13b`: `COMPLETED` in 3 minutes 42 seconds, one Worker attempt, `provider=openai_whisper`, 5 segments from 2.0 to 12.0 seconds, all inside the requested range. Titan delivered the full source, FFmpeg trimmed the range to MP3, and `whisper-1` returned segment timestamps. The Korean text is a forced-language transcription of English audio, which is expected for this test source and confirms the language hint is honoured.
- Both jobs advanced `next_step=CANDIDATE`; temporary media lives in a per-attempt `TemporaryDirectory` and is removed on exit.

Task 05 is complete. Task 06 may begin.
