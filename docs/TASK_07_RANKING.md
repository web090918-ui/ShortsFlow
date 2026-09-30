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
SHORTSFLOW_OPENAI_PROJECT=<optional OpenAI project id; only effective with an organization-scoped key>
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

Implemented on 2026-09-29 with 9 unit tests.

Cloud Run status on 2026-09-29: the ranking revision is live and the Worker reaches `step=RANKING` after transcript and candidates (job `57ab293b`, authorized Korean source `ZY-kQtE0WFE`, range 0-900 seconds, 15 candidates). The OpenAI call is rejected:

```text
HTTP 403 PermissionDeniedError:
Project `proj_U2Y72hXucvHowySPskoQnLzG` does not have access to model `gpt-4.1-mini`
```

The key and billing are valid (the same key completed `whisper-1` jobs the same day); the OpenAI project restricts which models it may use. Ranking failures are classified retryable, so the job used all three Cloud Tasks attempts before ending `FAILED` with the message above. The first two production attempts showed only the generic "AI 랭킹 요청에 실패했습니다" text; the ranker now includes the HTTP status, exception class, and the provider's message (never the key) so the cause is visible on the job.

Resolution on 2026-09-30: the key is organization-scoped, so `SHORTSFLOW_OPENAI_PROJECT=proj_InkVn5EtOT2q8LKO2v8bFE9X` (sent as the `OpenAI-Project` header on both the Whisper and ranking clients) moved the calls to a project that allows the model. No code path changed apart from passing the project id.

Cloud Run validation passed on 2026-09-30, job `6c6e8414` on the authorized Korean source `ZY-kQtE0WFE`, range 0-900 seconds:

- `COMPLETED` in 54 seconds (Titan captions, 15 candidates, ranking) with one Worker attempt, `step=RANKING`, `result.next_step=RENDER`, `ranker=openai:gpt-4.1-mini`, `criteria_version=generic_v1`.
- All 15 candidates scored, scores spread 15-78 with no ties in the top ten (78, 72, 70, 68, 67, 65, 62, 60, 58, 55, 50, 45, 40, 20, 15).
- Top 3 were three distinct moments (4-64 s, 862-900 s, 136-195 s) with no pairwise overlap above the 50 percent rule.
- Every reason was Korean and referred to the clip's own content, for example rank 1: "유럽 여행을 간다는 구체적 내용과 비행기의 경유 정보로 흥미를 유발하지만 초반 인사말이 다소 평범해 흥미도가 살짝 떨어집니다." The lowest score (15) went to a fragment whose hook was only "땡큐." with the reason that it has no hook and its content is disconnected.

Task 07 is complete. Task 08 may begin; its preview screen must label the number `AI Score` or `Recommended Score`.
