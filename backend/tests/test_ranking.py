import json

import pytest

from app.candidates import CandidateSet, ClipCandidate
from app.ranking import (
    HeuristicRanker,
    OpenAIRanker,
    RankingError,
    build_user_prompt,
    select_top,
)


def _candidate(index: int, start: float, end: float, *, text="말하는 내용") -> ClipCandidate:
    duration = end - start
    return ClipCandidate(
        id=f"cand-{index}",
        index=index,
        start_seconds=start,
        end_seconds=end,
        duration_seconds=duration,
        transcript_text=f"{text} {index} " * 5,
        hook_text=f"훅 문장 {index}",
        segment_count=3,
        word_count=15,
        words_per_second=round(15 / duration, 2),
        starts_on_sentence_boundary=index % 2 == 1,
        ends_on_sentence_boundary=True,
        leading_gap_seconds=0.5,
        trailing_gap_seconds=0.2,
    )


def _candidates(count: int = 5) -> CandidateSet:
    items = [_candidate(i, (i - 1) * 40, (i - 1) * 40 + 30) for i in range(1, count + 1)]
    return CandidateSet(
        generator="heuristic_v1",
        source_start_seconds=0,
        source_end_seconds=400,
        transcript_provider="apify_titan",
        language="ko",
        min_seconds=15,
        max_seconds=60,
        items=items,
    )


class FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        message = type("Message", (), {"content": self.content})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


class FakeOpenAI:
    def __init__(self, content: str) -> None:
        self.completions = FakeCompletions(content)
        self.chat = type("Chat", (), {"completions": self.completions})()


def _payload(scores: dict[int, int], **extra) -> str:
    return json.dumps(
        {
            "items": [
                {
                    "index": index,
                    "ai_score": score,
                    "reason": f"이유 {index}",
                    "strengths": ["강한 훅"],
                    "concerns": [],
                    **extra,
                }
                for index, score in scores.items()
            ]
        }
    )


def test_openai_ranker_orders_by_score_and_returns_top_3() -> None:
    client = FakeOpenAI(_payload({1: 55, 2: 91, 3: 70, 4: 88, 5: 30}))
    ranker = OpenAIRanker(client, model="test-model", reason_language="ko")

    result = ranker.rank(_candidates(), video_title="테스트 영상")

    assert result.ranker == "openai:test-model"
    assert result.criteria_version == "generic_v1"
    assert [item.index for item in result.items] == [2, 4, 3, 1, 5]
    assert [item.rank for item in result.items] == [1, 2, 3, 4, 5]
    assert [item.index for item in result.top_3] == [2, 4, 3]
    assert result.items[0].ai_score == 91
    assert result.items[0].reason == "이유 2"
    assert result.items[0].strengths == ["강한 훅"]
    assert result.items[0].hook_text == "훅 문장 2"
    kwargs = client.completions.kwargs
    assert kwargs["model"] == "test-model"
    assert kwargs["response_format"] == {"type": "json_object"}
    assert "테스트 영상" in kwargs["messages"][1]["content"]
    assert "Candidate 5" in kwargs["messages"][1]["content"]


def test_openai_ranker_clamps_scores_and_rejects_missing_candidates() -> None:
    clamped = OpenAIRanker(
        FakeOpenAI(_payload({1: 140, 2: -5, 3: 50, 4: 60, 5: 70})), model="m"
    ).rank(_candidates())
    by_index = {item.index: item.ai_score for item in clamped.items}
    assert by_index[1] == 100
    assert by_index[2] == 0

    with pytest.raises(RankingError) as excinfo:
        OpenAIRanker(FakeOpenAI(_payload({1: 80, 2: 70})), model="m").rank(_candidates())
    assert "3, 4, 5" in str(excinfo.value)
    assert excinfo.value.retryable is True

    with pytest.raises(RankingError):
        OpenAIRanker(FakeOpenAI("not json"), model="m").rank(_candidates())


def test_openai_ranker_wraps_client_failures_as_retryable() -> None:
    class FailingCompletions:
        def create(self, **kwargs):
            raise TimeoutError("slow")

    client = type("C", (), {})()
    client.chat = type("Chat", (), {"completions": FailingCompletions()})()

    with pytest.raises(RankingError) as excinfo:
        OpenAIRanker(client, model="m").rank(_candidates())
    assert excinfo.value.retryable is True
    assert "TimeoutError" in str(excinfo.value)
    assert "slow" in str(excinfo.value)


def test_openai_api_errors_surface_status_and_message_without_secrets() -> None:
    class FakeApiError(Exception):
        status_code = 404
        body = {
            "error": {
                "message": "The model `gpt-x` does not exist or you do not have access to it.",
                "code": "model_not_found",
            }
        }

    class FailingCompletions:
        def create(self, **kwargs):
            raise FakeApiError("sk-secret-should-not-appear")

    client = type("C", (), {})()
    client.chat = type("Chat", (), {"completions": FailingCompletions()})()

    with pytest.raises(RankingError) as excinfo:
        OpenAIRanker(client, model="gpt-x").rank(_candidates())

    message = str(excinfo.value)
    assert "HTTP 404" in message
    assert "FakeApiError" in message
    assert "does not exist or you do not have access" in message
    assert "sk-secret" not in message


def test_top_3_skips_heavily_overlapping_candidates() -> None:
    candidates = _candidates(3)
    # Candidate 2 overlaps candidate 1 almost entirely; candidate 3 is far away.
    candidates.items[1] = _candidate(2, 2, 32)
    ranker = OpenAIRanker(FakeOpenAI(_payload({1: 90, 2: 85, 3: 40})), model="m")

    result = ranker.rank(candidates)

    assert [item.index for item in result.top_3] == [1, 3, 2]


def test_select_top_falls_back_when_everything_overlaps() -> None:
    candidates = _candidates(3)
    candidates.items[1] = _candidate(2, 1, 31)
    candidates.items[2] = _candidate(3, 2, 32)
    ranked = OpenAIRanker(FakeOpenAI(_payload({1: 90, 2: 80, 3: 70})), model="m").rank(
        candidates
    )

    top = select_top(ranked.items, candidates, count=3)

    assert [item.index for item in top] == [1, 2, 3]


def test_user_prompt_truncates_long_text() -> None:
    candidates = _candidates(1)
    candidates.items[0] = candidates.items[0].model_copy(
        update={"transcript_text": "가" * 2000}
    )

    prompt = build_user_prompt(candidates, reason_language="ko", video_title=None)

    assert "Video title: unknown" in prompt
    assert "가" * 697 + "..." in prompt
    assert "가" * 800 not in prompt


def test_heuristic_ranker_is_deterministic_and_complete() -> None:
    ranker = HeuristicRanker()

    first = ranker.rank(_candidates())
    second = ranker.rank(_candidates())

    assert first.ranker == "heuristic_structural"
    assert [item.index for item in first.items] == [item.index for item in second.items]
    assert len(first.items) == 5
    assert len(first.top_3) == 3
    assert all(0 <= item.ai_score <= 100 for item in first.items)


def test_rankers_reject_empty_candidate_sets() -> None:
    empty = _candidates(0)

    with pytest.raises(RankingError) as excinfo:
        HeuristicRanker().rank(empty)
    assert excinfo.value.retryable is False


def test_openai_ranker_keeps_suggested_title_and_description() -> None:
    content = _payload(
        {1: 80, 2: 70, 3: 60, 4: 50, 5: 40},
        title='"독립을 위해 [목숨]을 건 여자"',
        description="  이 장면 어떻게 보셨나요?\n\n#쇼츠 #다큐  ",
    )
    result = OpenAIRanker(FakeOpenAI(content), model="gpt-test").rank(_candidates())

    first = result.items[0]
    assert first.title == "독립을 위해 [목숨]을 건 여자"
    assert first.description == "이 장면 어떻게 보셨나요?\n#쇼츠 #다큐"
    from app.ranking import SYSTEM_PROMPT

    assert "title" in SYSTEM_PROMPT and "description" in SYSTEM_PROMPT


def test_openai_ranker_tolerates_missing_suggestions() -> None:
    result = OpenAIRanker(FakeOpenAI(_payload({1: 80, 2: 70, 3: 60, 4: 50, 5: 40})), model="gpt-test").rank(
        _candidates()
    )

    assert all(item.title is None and item.description is None for item in result.items)


def test_heuristic_ranker_suggests_a_short_title_and_a_description() -> None:
    from app.ranking import suggest_title_from_hook

    assert suggest_title_from_hook("짧은 훅") == "짧은 훅"
    long_hook = "이 문장은 서른 글자를 훌쩍 넘기는 긴 설명이라 제목으로 쓰기에는 어울리지 않습니다"
    short = suggest_title_from_hook(long_hook)
    assert len(short) <= 30 and short.endswith("…") and not short[:-1].endswith(" ")

    result = HeuristicRanker().rank(_candidates())
    for item in result.items:
        assert item.title and len(item.title) <= 30
        assert item.description and "#쇼츠" in item.description
