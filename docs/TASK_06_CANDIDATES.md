# Task 06 Candidate Generation

## Scope

Task 06 turns the Task 05 transcript into 10-15 timestamped clip candidates that each stand alone as a Short. It does not score, rank, personalize, or render anything; Task 07 ranks these candidates and Task 08 renders the chosen one.

Candidate generation runs inside the same Worker attempt as the transcript. After `TranscriptProcessor` returns, the job's `step` moves to `CANDIDATE`, `HeuristicCandidateGenerator` runs on the in-memory transcript, and the job completes with both results:

```text
result.next_step = RENDER   (RANKING on jobs completed before Task 07)
result.transcript = { ... Task 05 ... }
result.ranking    = { ... Task 07 ... }
result.candidates.generator = heuristic_v1
result.candidates.min_seconds / max_seconds
result.candidates.items[] = {
  id, index,
  start_seconds, end_seconds, duration_seconds,   # absolute source-video time
  transcript_text, hook_text,
  segment_count, word_count, words_per_second,
  starts_on_sentence_boundary, ends_on_sentence_boundary,
  leading_gap_seconds, trailing_gap_seconds
}
```

No new queue, endpoint, or storage is introduced. `GET /processing-jobs/{id}` exposes the candidates through `result`.

## Method

The generator is deterministic and free of external calls, which keeps Task 06 cheap and testable and leaves judgement to Task 07:

1. **Speech units.** Consecutive transcript segments are merged into units. A unit closes at a sentence end (`. ! ?` and common Korean sentence-final endings such as `~습니다`, `~요`, `~죠`, because Korean auto-captions rarely carry punctuation), at a pause of 0.8 seconds or more, or when the unit would exceed 12 seconds.
2. **Windows.** For every unit as a start, windows are extended to about 30, 45, and 58 seconds and clamped to the 15-60 second Short range.
3. **Selection.** Windows that start on a sentence boundary are preferred. Windows are kept only if they overlap every already-kept window by at most 50 percent; the threshold relaxes to 75 and then 90 percent when fewer than 10 survive. More than 15 survivors are thinned evenly across the range so candidates cover the whole selection rather than clustering.
4. **Padding.** Each candidate is padded by up to 0.25 seconds into the surrounding pause, clamped to the selected source range and to the 60-second maximum.
5. **Fallback.** A selection shorter than 15 seconds of speech produces one candidate covering the whole range, so short inputs still flow to ranking.

Supporting fields exist for the next tasks: `transcript_text` and `hook_text` feed ranking prompts and captions, `words_per_second` and the boundary flags are cheap generic signals, and the gap fields let rendering trim silence.

## Configuration

```text
SHORTSFLOW_CANDIDATE_MIN_SECONDS=15
SHORTSFLOW_CANDIDATE_MAX_SECONDS=60
SHORTSFLOW_CANDIDATE_COUNT_MIN=10
SHORTSFLOW_CANDIDATE_COUNT_MAX=15
```

`CandidateGenerator` is a small Protocol; an LLM-backed generator can replace `HeuristicCandidateGenerator` later without changing the Worker or the persisted shape.

## Exclusions

- No Channel DNA, channel statistics, or any personalization.
- No AI scoring or Top 3 selection (Task 07).
- No rendering, captions, or template behaviour (Task 08).

## Validation

Task 06 is complete when:

1. The unit tests cover unit splitting, the 10-15 count on a ten-minute synthetic transcript, range and duration bounds, ordering, non-duplication, sentence-boundary preference, the short-range fallback, and the non-retryable empty-transcript error.
2. A Cloud Run transcript job completes with `step=CANDIDATE`, `result.next_step=RANKING`, and a populated `result.candidates`.
3. On an authorized source of at least ten minutes with captions, the production job returns between 10 and 15 candidates, all inside the requested range and between 15 and 60 seconds long.

## Validation result

Implemented on 2026-09-29 with 8 unit tests.

Cloud Run check 2 passed on 2026-09-29: transcript job `bc55b543` on the 19-second test video `jNQXAC9IVRw` (range 2-12 seconds, English captions via Titan) completed with `step=CANDIDATE`, `result.next_step=RANKING`, `generator=heuristic_v1`, and one candidate covering 2.0-12.0 seconds with 26 words and a sentence-boundary start. One candidate is the expected short-range fallback because the selection is under 15 seconds.

Cloud Run check 3 passed on 2026-09-29: transcript job `5326e232` on the authorized Korean source `ZY-kQtE0WFE` (27 minutes 43 seconds, Korean captions via Titan), range 0-900 seconds. The Worker completed in 29 seconds with 331 caption segments and 15 candidates: all inside 0-900 seconds, all between 34.8 and 59.8 seconds long, ordered by start, and all starting on a sentence boundary. Hook texts were readable Korean sentences except where the caption itself was a sound tag (`[음악]`) or a `>>` speaker marker; those markers are now stripped from candidate text before unit building.

Task 06 is complete. Task 07 may begin.
