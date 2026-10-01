"""Task 07: Generic AI Ranking of clip candidates and Top 3 selection.

Scores come from generic, channel-agnostic criteria (hook, self-containment,
clarity, payoff, pacing). Nothing here reads channel data; the personal ranking
of MVP2 is a different feature. User-facing copy calls the number ``AI Score``.
"""

import json
import logging
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.candidates import CandidateSet, ClipCandidate, SpeechUnit


logger = logging.getLogger(__name__)
CRITERIA_VERSION = "generic_v2"
MAX_TEXT_CHARS = 700
MAX_CONTEXT_CHARS = 240
# A boundary may move at most this far, and only onto a speech-unit edge: the model
# fixes a cut that dropped a setup or a punchline, it does not pick a different clip.
MAX_BOUNDARY_SHIFT_SECONDS = 12.0


class RankingError(RuntimeError):
    """The ranker could not produce a complete result; the Worker may retry."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class RankedCandidate(BaseModel):
    candidate_id: str
    index: int = Field(ge=1)
    rank: int = Field(ge=1)
    ai_score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1)
    strengths: list[str] = []
    concerns: list[str] = []
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    hook_text: str
    # Suggested upload metadata the user can edit before rendering; the title is also
    # the on-video headline ([brackets] mark the coloured keyword).
    title: str | None = None
    description: str | None = None
    # True when the ranker moved the start or end onto a nearby speech-unit boundary
    # so the clip no longer opens or closes mid-thought.
    boundary_adjusted: bool = False


MAX_TITLE_CHARS = 100
MAX_DESCRIPTION_CHARS = 500


class RankingResult(BaseModel):
    ranker: str
    criteria_version: str
    reason_language: str
    items: list[RankedCandidate]
    top_3: list[RankedCandidate]


class CandidateRanker(Protocol):
    def rank(
        self,
        candidates: CandidateSet,
        *,
        video_title: str | None = None,
        reason_language: str | None = None,
    ) -> RankingResult: ...


def _overlap_ratio(a: ClipCandidate, b: ClipCandidate) -> float:
    overlap = max(0.0, min(a.end_seconds, b.end_seconds) - max(a.start_seconds, b.start_seconds))
    shorter = min(a.duration_seconds, b.duration_seconds)
    return overlap / shorter if shorter > 0 else 1.0


def select_top(
    ranked: list[RankedCandidate],
    candidates: CandidateSet,
    *,
    count: int = 3,
    max_overlap: float = 0.5,
) -> list[RankedCandidate]:
    """Take the best-scored candidates while keeping the picks distinct in time."""
    by_id = {item.id: item for item in candidates.items}
    picked: list[RankedCandidate] = []
    for item in ranked:
        candidate = by_id[item.candidate_id]
        if all(
            _overlap_ratio(candidate, by_id[other.candidate_id]) <= max_overlap
            for other in picked
        ):
            picked.append(item)
        if len(picked) >= count:
            break
    if len(picked) < count:
        for item in ranked:
            if item not in picked:
                picked.append(item)
            if len(picked) >= count:
                break
    return picked


def _snap(value: float, edges: list[float], *, anchor: float) -> float | None:
    """Nearest speech-unit edge to ``value`` that stays within reach of the original."""
    if not edges:
        return None
    nearest = min(edges, key=lambda edge: abs(edge - value))
    if abs(nearest - anchor) > MAX_BOUNDARY_SHIFT_SECONDS:
        return None
    return nearest


def adjust_boundaries(
    candidate: ClipCandidate,
    candidates: CandidateSet,
    *,
    start: float | None,
    end: float | None,
) -> tuple[float, float, str, bool]:
    """Apply a ranker's start/end suggestion, snapped to unit edges and length limits.

    Returns (start, end, hook_text, adjusted). Anything the model got wrong, such as a
    boundary off any unit edge, a shift too far, or a length outside the Short limits,
    falls back to the original clip rather than failing the job.
    """
    units = candidates.units
    original = (candidate.start_seconds, candidate.end_seconds, candidate.hook_text, False)
    if not units or (start is None and end is None):
        return original
    new_start = candidate.start_seconds
    new_end = candidate.end_seconds
    if start is not None:
        snapped = _snap(start, [u.start_seconds for u in units], anchor=candidate.start_seconds)
        if snapped is not None:
            new_start = snapped
    if end is not None:
        snapped = _snap(end, [u.end_seconds for u in units], anchor=candidate.end_seconds)
        if snapped is not None:
            new_end = snapped
    new_start = max(candidates.source_start_seconds, new_start)
    new_end = min(candidates.source_end_seconds, new_end)
    duration = new_end - new_start
    if not (candidates.min_seconds <= duration <= candidates.max_seconds):
        return original
    if (new_start, new_end) == (candidate.start_seconds, candidate.end_seconds):
        return original
    first = next((u for u in units if u.start_seconds >= new_start - 0.05), None)
    hook = candidate.hook_text
    if first is not None and first.start_seconds < new_end:
        hook = first.text if len(first.text) <= 80 else first.text[:77].rstrip() + "..."
    return round(new_start, 3), round(new_end, 3), hook, True


def _finish(
    scored: dict[int, dict[str, Any]],
    candidates: CandidateSet,
    *,
    ranker: str,
    reason_language: str,
    top_count: int,
) -> RankingResult:
    ordered = sorted(
        candidates.items,
        key=lambda item: (-scored[item.index]["ai_score"], item.start_seconds),
    )
    ranked = []
    for position, item in enumerate(ordered, start=1):
        entry = scored[item.index]
        start, end, hook, adjusted = adjust_boundaries(
            item, candidates, start=entry.get("start_seconds"), end=entry.get("end_seconds")
        )
        ranked.append(
            RankedCandidate(
                candidate_id=item.id,
                index=item.index,
                rank=position,
                ai_score=entry["ai_score"],
                reason=entry["reason"],
                strengths=entry.get("strengths", []),
                concerns=entry.get("concerns", []),
                start_seconds=start,
                end_seconds=end,
                duration_seconds=round(end - start, 3),
                hook_text=hook,
                title=entry.get("title"),
                description=entry.get("description"),
                boundary_adjusted=adjusted,
            )
        )
    return RankingResult(
        ranker=ranker,
        criteria_version=CRITERIA_VERSION,
        reason_language=reason_language,
        items=ranked,
        top_3=select_top(ranked, candidates, count=top_count),
    )


def _clean_text(value: Any, limit: int) -> str | None:
    """Trim a model-suggested string; None when missing or empty."""
    if not isinstance(value, str):
        return None
    lines = [" ".join(line.split()) for line in value.replace("\r", "").split("\n")]
    cleaned = "\n".join(line for line in lines if line).strip().strip('"\u201c\u201d')
    if not cleaned:
        return None
    return cleaned[:limit].rstrip()


def suggest_title_from_hook(hook_text: str, *, limit: int = 30) -> str:
    """Headline fallback without a model: the hook, cut at a word boundary."""
    hook = " ".join(hook_text.split())
    if len(hook) <= limit:
        return hook
    cut = hook[: limit - 1]
    if " " in cut[limit // 2 :]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,.!?") + "\u2026"


def _clamp_score(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, min(100, round(value)))


def _seconds(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _string_list(value: Any, limit: int = 3) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(entry).strip() for entry in value if str(entry).strip()][:limit]


def _describe_client_error(exc: Exception) -> str:
    """Build an actionable message from an OpenAI SDK error without leaking secrets."""
    status_code = getattr(exc, "status_code", None)
    detail = ""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict):
            detail = str(error.get("message") or error.get("code") or "")
    if not detail:
        detail = str(exc)
    detail = " ".join(detail.split())[:200]
    prefix = "AI 랭킹 요청에 실패했습니다"
    if status_code is not None:
        prefix += f" (HTTP {status_code}, {exc.__class__.__name__})"
    else:
        prefix += f" ({exc.__class__.__name__})"
    return f"{prefix}: {detail}" if detail else f"{prefix}."


SYSTEM_PROMPT = """You rank candidate clips cut from one long video for publication as
standalone vertical Shorts. Judge each candidate ONLY on generic criteria that apply
to any creator; you know nothing about the channel or its audience:

1. Hook: do the first one or two sentences make a viewer stop scrolling?
2. Self-contained: is it understandable with no context from the rest of the video?
   Watch for openings that lean on what came just before ("so", "that's why", "그래서",
   "그게") and endings that stop before the point lands.
3. Complete thought: does it start and end cleanly rather than mid-idea?
4. Payoff: does it deliver something concrete (insight, emotion, surprise, useful fact)?
5. Pacing: is the speech dense and lively rather than filler, silence, or rambling?

Score every candidate from 0 to 100 as an integer ("ai_score"). Use the full range and
avoid ties where possible. Give one concise reason (max two sentences) in the requested
language that a creator can act on, plus up to three short strengths and concerns.

Also propose, in the requested language, upload metadata for each candidate:
- "title": a punchy Shorts headline of at most 30 characters, no quotation marks, that
  states the payoff or the question the clip answers. Wrap the single most important
  word or phrase in square brackets, e.g. "독립을 위해 [목숨]을 건 여자"; it is shown in
  a highlight colour on the video. You may split it into two lines with "\n".
- "description": one or two sentences (at most 150 characters) inviting viewers to
  watch or comment, followed by two or three relevant hashtags.

Each candidate also lists the speech just before and after it, with the time at which
each of those speech units starts and ends. If the clip would read as a complete
thought by starting one or two units earlier, or ending one or two units later or
earlier, say so with "start_seconds" and/or "end_seconds" set to one of the listed
unit boundaries. Only do this to fix a cut that opens or closes mid-thought; never
move a boundary more than about 10 seconds, and keep the clip between the stated
minimum and maximum length. Omit both fields when the cut is already clean. Score
the clip as it would be after your adjustment.

Return JSON only, shaped as:
{"items":[{"index":1,"ai_score":82,"reason":"...","strengths":["..."],"concerns":["..."],
"title":"...","description":"...","start_seconds":123.4,"end_seconds":161.0}]}
Include every candidate index exactly once."""


def _neighbour_units(
    candidate: ClipCandidate, units: list[SpeechUnit], *, before: bool, count: int = 2
) -> str:
    """Timestamped neighbouring units for the prompt; falls back to the plain context text."""
    if before:
        picked = [u for u in units if u.end_seconds <= candidate.start_seconds + 0.05][-count:]
    else:
        picked = [u for u in units if u.start_seconds >= candidate.end_seconds - 0.05][:count]
    if not picked:
        text = candidate.context_before if before else candidate.context_after
        return text[:MAX_CONTEXT_CHARS] if text else "(none)"
    parts = []
    for unit in picked:
        text = unit.text
        if len(text) > MAX_CONTEXT_CHARS // count:
            text = text[: MAX_CONTEXT_CHARS // count - 3].rstrip() + "..."
        parts.append(f"[{unit.start_seconds:.1f}-{unit.end_seconds:.1f}s] {text}")
    return " | ".join(parts)


def build_user_prompt(
    candidates: CandidateSet, *, reason_language: str, video_title: str | None
) -> str:
    lines = [
        f"Reason language: {reason_language}",
        f"Transcript language: {candidates.language or 'unknown'}",
        f"Video title: {video_title or 'unknown'}",
        f"Selected source range: {candidates.source_start_seconds:.0f}-{candidates.source_end_seconds:.0f} seconds",
        f"Clip length limits: {candidates.min_seconds:.0f}-{candidates.max_seconds:.0f} seconds",
        f"Candidates: {len(candidates.items)}",
        "",
    ]
    for item in candidates.items:
        text = item.transcript_text
        if len(text) > MAX_TEXT_CHARS:
            text = text[: MAX_TEXT_CHARS - 3].rstrip() + "..."
        lines += [
            f"### Candidate {item.index}",
            f"time: {item.start_seconds:.1f}-{item.end_seconds:.1f}s ({item.duration_seconds:.1f}s), "
            f"words/sec: {item.words_per_second}, "
            f"starts_on_sentence: {item.starts_on_sentence_boundary}, "
            f"ends_on_sentence: {item.ends_on_sentence_boundary}",
            f"hook: {item.hook_text}",
            f"text: {text}",
            f"before: {_neighbour_units(item, candidates.units, before=True)}",
            f"after: {_neighbour_units(item, candidates.units, before=False)}",
            "",
        ]
    return "\n".join(lines)


class OpenAIRanker:
    def __init__(
        self,
        client: Any,
        *,
        model: str,
        reason_language: str = "ko",
        top_count: int = 3,
    ) -> None:
        self._client = client
        self._model = model
        self._reason_language = reason_language
        self._top_count = top_count

    def rank(
        self,
        candidates: CandidateSet,
        *,
        video_title: str | None = None,
        reason_language: str | None = None,
    ) -> RankingResult:
        if not candidates.items:
            raise RankingError("랭킹할 후보가 없습니다.", retryable=False)
        language = reason_language or self._reason_language
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_user_prompt(
                            candidates,
                            reason_language=language,
                            video_title=video_title,
                        ),
                    },
                ],
            )
            content = response.choices[0].message.content
        except Exception as exc:
            logger.warning("AI ranking request failed", exc_info=exc)
            raise RankingError(_describe_client_error(exc)) from exc

        try:
            payload = json.loads(content or "")
        except json.JSONDecodeError as exc:
            raise RankingError("AI 랭킹 응답을 해석하지 못했습니다.") from exc
        raw_items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(raw_items, list):
            raise RankingError("AI 랭킹 응답에 항목이 없습니다.")

        scored: dict[int, dict[str, Any]] = {}
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            index = raw.get("index")
            score = _clamp_score(raw.get("ai_score"))
            reason = str(raw.get("reason") or "").strip()
            if not isinstance(index, int) or score is None or not reason:
                continue
            scored[index] = {
                "ai_score": score,
                "reason": reason,
                "strengths": _string_list(raw.get("strengths")),
                "concerns": _string_list(raw.get("concerns")),
                "title": _clean_text(raw.get("title"), MAX_TITLE_CHARS),
                "description": _clean_text(raw.get("description"), MAX_DESCRIPTION_CHARS),
                "start_seconds": _seconds(raw.get("start_seconds")),
                "end_seconds": _seconds(raw.get("end_seconds")),
            }
        missing = [item.index for item in candidates.items if item.index not in scored]
        if missing:
            raise RankingError(f"AI 랭킹 응답에 후보 {missing}의 점수가 없습니다.")
        return _finish(
            scored,
            candidates,
            ranker=f"openai:{self._model}",
            reason_language=language,
            top_count=self._top_count,
        )


class HeuristicRanker:
    """Development-only stand-in when no OpenAI key is configured.

    It scores structural signals only (sentence boundaries, pacing, hook length) so
    the pipeline can run end to end locally. It is not the product's AI Score.
    """

    def __init__(self, *, reason_language: str = "ko", top_count: int = 3) -> None:
        self._reason_language = reason_language
        self._top_count = top_count

    def rank(
        self,
        candidates: CandidateSet,
        *,
        video_title: str | None = None,
        reason_language: str | None = None,
    ) -> RankingResult:
        if not candidates.items:
            raise RankingError("랭킹할 후보가 없습니다.", retryable=False)
        scored: dict[int, dict[str, Any]] = {}
        for item in candidates.items:
            score = 40
            score += 15 if item.starts_on_sentence_boundary else 0
            score += 15 if item.ends_on_sentence_boundary else 0
            pace = item.words_per_second
            score += 20 if 1.2 <= pace <= 3.0 else 8 if pace > 0.6 else 0
            score += 10 if 20 <= len(item.hook_text) <= 80 else 0
            scored[item.index] = {
                "ai_score": max(0, min(100, score)),
                "reason": "문장 경계와 발화 밀도 기준의 구조 점수입니다 (개발용 대체 랭커).",
                "strengths": [],
                "concerns": [],
                "title": suggest_title_from_hook(item.hook_text),
                "description": f"{item.hook_text} 이 장면, 어떻게 보셨나요? 댓글로 알려 주세요! #쇼츠 #하이라이트"[
                    :MAX_DESCRIPTION_CHARS
                ],
            }
        return _finish(
            scored,
            candidates,
            ranker="heuristic_structural",
            reason_language=reason_language or self._reason_language,
            top_count=self._top_count,
        )
