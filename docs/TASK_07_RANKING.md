# Task 07 Generic AI Ranking

## Scope

Task 07 scores the Task 06 candidates with generic, channel-agnostic criteria and returns the Top 3 with concise recommendation reasons. It is the MVP1 "Generic AI Ranking"; the user-facing number is called **AI Score**. It is not Personal Virality Score, reads no channel data, and does not render.

Ranking runs in the same Worker attempt as the transcript and candidates. After candidates are generated the job's `step` moves to `RANKING`, the ranker scores every candidate, and the job completes with:

```text
result.next_step = RENDER
result.ranking.ranker            = openai:<model> | heuristic_structural (dev only)
result.ranking.criteria_version  = generic_v1
result.ranking.reason_language   = ko
result.ranking.items[]           = every candidate, sorted by ai_score desc:
  { candidate_id, index, rank, ai_score (0-100), reason, strengths[], concerns[],
    start_seconds, end_seconds, duration_seconds, hook_text }
result.ranking.top_3[]           = up to three items, best first, kept distinct in time
```

## Criteria

The prompt asks the model to judge each candidate only on signals that apply to any creator:

1. Hook: do the first one or two sentences stop the scroll?
2. Self-contained: understandable without the rest of the video.
3. Complete thought: clean start and end.
4. Payoff: a concrete insight, emotion, surprise, or useful fact.
5. Pacing: dense, lively speech rather than filler or silence.

Scores are integers from 0 to 100 with the full range encouraged. Each candidate gets one actionable reason of at most two sentences in `SHORTSFLOW_RANKING_REASON_LANGUAGE` plus up to three strengths and concerns.

## Top 3 selection

Candidates are taken in score order, skipping any that overlaps an already-picked candidate by more than half of the shorter clip, so the Top 3 are three different moments rather than three cuts of the same one. If fewer than three distinct candidates exist the remaining slots are filled in score order.

## Provider and failure handling

- `OpenAIRanker` calls Chat Completions with `response_format=json_object` using the existing `SHORTSFLOW_OPENAI_API_KEY`; the model is `SHORTSFLOW_OPENAI_RANKING_MODEL` (default `gpt-4.1-mini`). Candidate text is truncated to 700 characters each, so 15 candidates stay around 10k input tokens.
- Missing or malformed scores raise a retryable `RankingError`, so the Cloud Tasks attempt is retried up to the configured limit rather than persisting a partial ranking. Scores outside 0-100 are clamped.
- Without an OpenAI key the Worker uses `HeuristicRanker`, a structural stand-in (sentence boundaries, pacing, hook length) that keeps local development runnable. Its result is labelled `heuristic_structural` and is not the product's AI Score.
- `CandidateRanker` is a small Protocol; a different model vendor or a fine-tuned ranker replaces `OpenAIRanker` without touching the Worker or the persisted shape.

## Configuration

```text
SHORTSFLOW_OPENAI_API_KEY=<server-only secret, already configured for Whisper>
SHORTSFLOW_OPENAI_RANKING_MODEL=gpt-4.1-mini
SHORTSFLOW_RANKING_REASON_LANGUAGE=ko
SHORTSFLOW_RANKING_TOP_COUNT=3
```

## Exclusions

- No Channel DNA, channel statistics, audience data, or Personal Virality Score.
- No rendering, captions, or template behaviour (Task 08).
- No UI for browsing the Top 3 yet; Task 08 adds the preview and selection screen, which must label the number `AI Score` or `Recommended Score`.

## Validation

Task 07 is complete when:

1. Unit tests cover score ordering, clamping, missing-candidate rejection, client failure wrapping, Top 3 distinctness, prompt truncation, and the development ranker.
2. A Cloud Run job on an authorized source of at least ten minutes completes with `step=RANKING`, `result.next_step=RENDER`, `ranker=openai:<model>`, one score and reason per candidate, and a Top 3 whose members do not overlap.
3. The reasons are in the configured language and refer to the clip's content.

## Validation result

Implemented on 2026-09-29 with 8 unit tests. Production checks are recorded below once run.
