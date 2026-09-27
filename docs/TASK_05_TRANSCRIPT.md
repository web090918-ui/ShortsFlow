# Task 05 Transcript

## Scope

Task 05 produces a timestamped transcript for the user-selected YouTube source range. It does not generate clip candidates, rank content, or render video.

The production order is:

1. Request timestamped Tunelio captions.
2. Filter captions to the selected source range.
3. If captions are unavailable for that range, acquire the 480p range and extract a temporary MP3 with FFmpeg.
4. Send the MP3 to OpenAI `whisper-1` with segment timestamps.
5. Normalize timestamps to the original source-video timeline and persist the result in Firestore.

Tunelio documents `/transcript` as a six-credit request and says repeated unique-video requests may be cached by the provider. ShortsFlow also caches successful caption responses for six hours in each warm process. Failed requests are not cached. Current provider behavior and pricing can change; see <https://tunelio.dev/docs/>.

OpenAI accepts transcription files up to 25 MB and requires `whisper-1` for segment or word timestamp granularities. The fallback MP3 uses mono 16 kHz audio at 32 kbps so the maximum 60-minute selection remains below that upload limit. See <https://developers.openai.com/api/docs/guides/speech-to-text>.

## Cloud Run secrets

Configure these values as secrets or secret-backed environment variables. Never commit their values.

```text
SHORTSFLOW_TUNELIO_API_KEY=<server-only key>
SHORTSFLOW_OPENAI_API_KEY=<server-only key>
SHORTSFLOW_OPENAI_STT_MODEL=whisper-1
```

The Tunelio key is required for Task 05. The OpenAI key is optional only when every processed range has usable captions; without it, a captionless range fails with an actionable error instead of silently skipping transcript generation.

## Persisted result

A completed `ProcessingJob` stores:

```text
result.next_step = CANDIDATE
result.transcript.provider = tunelio | openai_whisper
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

1. A source range with captions completes with `provider=tunelio` without media acquisition or an OpenAI call.
2. A source range without captions downloads only the selected 480p proxy, extracts audio with FFmpeg, and completes with `provider=openai_whisper`.
3. Both results contain non-empty timestamped segments within the requested range.
4. `next_step` is `CANDIDATE`.
5. Provider authentication, quota, media download, FFmpeg, and STT failures persist an actionable job error.
6. Temporary media is removed after each fallback attempt.

Do not start Task 06 until these production checks pass.
