"""Task 06: turn a timestamped transcript into 10-15 standalone clip candidates.

This is a deterministic segmentation step. It groups transcript segments into
speech units at sentence ends and pauses, slides Short-length windows over those
units, and keeps a diverse, non-redundant set. Ranking (Task 07) decides which
candidates are good; this module only guarantees that each candidate is a
well-formed, self-contained range with the text needed to rank and render it.
"""

import re
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from app.transcripts import TranscriptResult, TranscriptSegment


GENERATOR_VERSION = "heuristic_v1"

_SENTENCE_END = re.compile(r"[.!?。！？…]+[\"'”’)\]]*$")
# Korean captions rarely carry punctuation; common sentence-final endings stand in.
_KOREAN_SENTENCE_END = re.compile(r"(습니다|입니다|니다|세요|네요|군요|거든요|는데요|죠|다|요|까)$")


class ClipCandidate(BaseModel):
    id: str
    index: int = Field(ge=1)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    duration_seconds: float = Field(gt=0)
    transcript_text: str = Field(min_length=1)
    hook_text: str = Field(min_length=1)
    segment_count: int = Field(ge=1)
    word_count: int = Field(ge=1)
    words_per_second: float = Field(ge=0)
    starts_on_sentence_boundary: bool
    ends_on_sentence_boundary: bool
    leading_gap_seconds: float = Field(ge=0)
    trailing_gap_seconds: float = Field(ge=0)


class CandidateSet(BaseModel):
    generator: str
    source_start_seconds: float
    source_end_seconds: float
    transcript_provider: str
    language: str | None
    min_seconds: float
    max_seconds: float
    items: list[ClipCandidate]


class CandidateGenerator(Protocol):
    def generate(self, transcript: TranscriptResult) -> CandidateSet: ...


class CandidateGenerationError(RuntimeError):
    """No usable candidate could be produced; retrying the Worker would not help."""

    retryable = False


@dataclass
class _Unit:
    start: float
    end: float
    text: str
    segment_count: int = 1
    sentence_end: bool = False
    gap_after: float = 0.0
    gap_before: float = 0.0
    parts: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start


def _ends_sentence(text: str) -> bool:
    stripped = text.rstrip()
    return bool(_SENTENCE_END.search(stripped) or _KOREAN_SENTENCE_END.search(stripped))


def build_units(
    segments: list[TranscriptSegment],
    *,
    gap_threshold: float = 0.8,
    max_unit_seconds: float = 12.0,
) -> list[_Unit]:
    """Merge consecutive segments into sentence-or-pause bounded speech units."""
    ordered = sorted(segments, key=lambda item: (item.start_seconds, item.end_seconds))
    units: list[_Unit] = []
    current: _Unit | None = None
    for segment in ordered:
        text = " ".join(segment.text.split())
        if not text:
            continue
        if current is None:
            current = _Unit(segment.start_seconds, segment.end_seconds, text)
        else:
            gap = max(0.0, segment.start_seconds - current.end)
            would_exceed = segment.end_seconds - current.start > max_unit_seconds
            if current.sentence_end or gap >= gap_threshold or would_exceed:
                current.gap_after = gap
                units.append(current)
                current = _Unit(segment.start_seconds, segment.end_seconds, text, gap_before=gap)
            else:
                current.end = max(current.end, segment.end_seconds)
                current.text = f"{current.text} {text}"
                current.segment_count += 1
        current.sentence_end = _ends_sentence(current.text)
    if current is not None:
        units.append(current)
    return units


def _overlap_ratio(a: tuple[float, float], b: tuple[float, float]) -> float:
    overlap = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    shorter = min(a[1] - a[0], b[1] - b[0])
    return overlap / shorter if shorter > 0 else 1.0


def _evenly_spaced(items: list, count: int) -> list:
    if len(items) <= count:
        return items
    if count == 1:
        return [items[0]]
    picked = []
    step = (len(items) - 1) / (count - 1)
    for position in range(count):
        picked.append(items[round(position * step)])
    return picked


class HeuristicCandidateGenerator:
    def __init__(
        self,
        *,
        min_seconds: float = 15.0,
        max_seconds: float = 60.0,
        target_lengths: tuple[float, ...] = (30.0, 45.0, 58.0),
        target_count_min: int = 10,
        target_count_max: int = 15,
        padding_seconds: float = 0.25,
        gap_threshold: float = 0.8,
    ) -> None:
        if min_seconds <= 0 or max_seconds <= min_seconds:
            raise ValueError("max_seconds must be greater than min_seconds")
        if target_count_min < 1 or target_count_max < target_count_min:
            raise ValueError("invalid target counts")
        self._min = min_seconds
        self._max = max_seconds
        self._targets = tuple(
            sorted({min(max(length, min_seconds), max_seconds) for length in target_lengths})
        )
        self._count_min = target_count_min
        self._count_max = target_count_max
        self._padding = padding_seconds
        self._gap_threshold = gap_threshold

    def _windows(self, units: list[_Unit]) -> list[tuple[int, int]]:
        windows: set[tuple[int, int]] = set()
        for i in range(len(units)):
            for target in self._targets:
                j = i
                while j + 1 < len(units) and units[j].end - units[i].start < target:
                    j += 1
                while j > i and units[j].end - units[i].start > self._max:
                    j -= 1
                duration = units[j].end - units[i].start
                if self._min <= duration <= self._max:
                    windows.add((i, j))
        return sorted(windows)

    def _starts_boundary(self, units: list[_Unit], i: int) -> bool:
        return i == 0 or units[i - 1].sentence_end or units[i].gap_before >= self._gap_threshold

    def _select(
        self, units: list[_Unit], windows: list[tuple[int, int]]
    ) -> list[tuple[int, int]]:
        def span(window: tuple[int, int]) -> tuple[float, float]:
            return units[window[0]].start, units[window[1]].end

        # Sentence-boundary starts first, then everything else; within each group by start.
        ordered = sorted(
            windows,
            key=lambda w: (not self._starts_boundary(units, w[0]), span(w)[0], -(span(w)[1])),
        )
        selected: list[tuple[int, int]] = []
        for threshold in (0.5, 0.75, 0.9):
            for window in ordered:
                if window in selected:
                    continue
                if all(_overlap_ratio(span(window), span(kept)) <= threshold for kept in selected):
                    selected.append(window)
            if len(selected) >= self._count_min:
                break
        selected.sort(key=lambda w: (span(w)[0], span(w)[1]))
        if len(selected) > self._count_max:
            selected = _evenly_spaced(selected, self._count_max)
        return selected

    def generate(self, transcript: TranscriptResult) -> CandidateSet:
        range_start = transcript.source_start_seconds
        range_end = transcript.source_end_seconds
        units = build_units(transcript.segments, gap_threshold=self._gap_threshold)
        if not units:
            raise CandidateGenerationError("후보를 만들 수 있는 자막이나 음성이 없습니다.")

        windows = self._windows(units)
        if windows:
            selected = self._select(units, windows)
        else:
            # The whole range is shorter than a minimum Short: offer it as one candidate.
            selected = [(0, len(units) - 1)]

        items: list[ClipCandidate] = []
        for index, (i, j) in enumerate(selected, start=1):
            first, last = units[i], units[j]
            start = max(range_start, first.start - min(self._padding, first.gap_before))
            end = min(range_end, last.end + min(self._padding, last.gap_after or self._padding))
            if end - start > self._max:
                end = start + self._max
            if end <= start:
                continue
            text = " ".join(unit.text for unit in units[i : j + 1])
            words = text.split()
            duration = round(end - start, 3)
            hook = first.text if len(first.text) <= 80 else first.text[:77].rstrip() + "..."
            items.append(
                ClipCandidate(
                    id=str(uuid4()),
                    index=index,
                    start_seconds=round(start, 3),
                    end_seconds=round(end, 3),
                    duration_seconds=duration,
                    transcript_text=text,
                    hook_text=hook,
                    segment_count=sum(unit.segment_count for unit in units[i : j + 1]),
                    word_count=len(words),
                    words_per_second=round(len(words) / duration, 2) if duration else 0.0,
                    starts_on_sentence_boundary=self._starts_boundary(units, i),
                    ends_on_sentence_boundary=last.sentence_end or j == len(units) - 1,
                    leading_gap_seconds=round(first.gap_before, 3),
                    trailing_gap_seconds=round(last.gap_after, 3),
                )
            )
        if not items:
            raise CandidateGenerationError("후보 구간을 만들지 못했습니다.")
        return CandidateSet(
            generator=GENERATOR_VERSION,
            source_start_seconds=range_start,
            source_end_seconds=range_end,
            transcript_provider=transcript.provider,
            language=transcript.language,
            min_seconds=self._min,
            max_seconds=self._max,
            items=items,
        )
