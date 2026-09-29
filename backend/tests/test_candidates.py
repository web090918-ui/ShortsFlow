import pytest

from app.candidates import (
    CandidateGenerationError,
    HeuristicCandidateGenerator,
    build_units,
)
from app.transcripts import TranscriptResult, TranscriptSegment


def _transcript(segments, *, start, end, language="ko") -> TranscriptResult:
    return TranscriptResult(
        provider="apify_titan",
        language=language,
        is_generated=False,
        source_start_seconds=start,
        source_end_seconds=end,
        segments=segments,
        full_text=" ".join(segment.text for segment in segments),
    )


def _speech(start: float, end: float, *, seconds_per_segment=3.0, pause_every=5):
    """Synthetic Korean-style captions: 3-second segments, a pause every N segments."""
    segments = []
    cursor = start
    counter = 0
    while cursor + seconds_per_segment <= end:
        counter += 1
        text = f"문장 {counter} 입니다" if counter % 2 == 0 else f"이야기 {counter} 계속"
        segments.append(
            TranscriptSegment(
                start_seconds=cursor, end_seconds=cursor + seconds_per_segment, text=text
            )
        )
        cursor += seconds_per_segment
        if counter % pause_every == 0:
            cursor += 1.2  # pause longer than the gap threshold
    return segments


def test_build_units_breaks_on_sentence_end_pause_and_length() -> None:
    segments = [
        TranscriptSegment(start_seconds=0, end_seconds=2, text="Hello there"),
        TranscriptSegment(start_seconds=2, end_seconds=4, text="how are you?"),
        TranscriptSegment(start_seconds=4.1, end_seconds=6, text="I am fine"),
        TranscriptSegment(start_seconds=7.5, end_seconds=9, text="after a pause"),
        TranscriptSegment(start_seconds=9, end_seconds=20, text="very long tail segment"),
        TranscriptSegment(start_seconds=20, end_seconds=22, text="overflow"),
    ]

    units = build_units(segments)

    # The 11-second tail would push its unit past the 12-second cap, so it stands alone.
    assert [unit.text for unit in units] == [
        "Hello there how are you?",
        "I am fine",
        "after a pause",
        "very long tail segment",
        "overflow",
    ]
    assert units[0].sentence_end is True
    assert units[2].gap_before == pytest.approx(1.5)
    assert units[1].gap_after == pytest.approx(1.5)


def test_generates_ten_to_fifteen_candidates_for_a_ten_minute_range() -> None:
    transcript = _transcript(_speech(120, 720), start=120, end=720)
    generator = HeuristicCandidateGenerator()

    result = generator.generate(transcript)

    assert result.generator == "heuristic_v1"
    assert result.transcript_provider == "apify_titan"
    assert 10 <= len(result.items) <= 15
    starts = [item.start_seconds for item in result.items]
    assert starts == sorted(starts)
    assert [item.index for item in result.items] == list(range(1, len(result.items) + 1))
    for item in result.items:
        assert 120 <= item.start_seconds < item.end_seconds <= 720
        assert 15 <= item.duration_seconds <= 60
        assert item.duration_seconds == pytest.approx(item.end_seconds - item.start_seconds, abs=0.01)
        assert item.transcript_text
        assert item.hook_text
        assert item.word_count >= 1
        assert item.words_per_second > 0
    # Candidates cover the range rather than clustering at the start.
    assert result.items[-1].end_seconds > 600
    # Candidates are distinct clips, not near duplicates of each other.
    for first, second in zip(result.items, result.items[1:]):
        overlap = max(0.0, first.end_seconds - second.start_seconds)
        assert overlap <= 0.9 * min(first.duration_seconds, second.duration_seconds)


def test_candidates_prefer_sentence_boundaries_and_expose_context() -> None:
    transcript = _transcript(_speech(0, 400), start=0, end=400)

    result = HeuristicCandidateGenerator().generate(transcript)

    boundary_starts = [item for item in result.items if item.starts_on_sentence_boundary]
    assert len(boundary_starts) >= len(result.items) // 2
    first = result.items[0]
    assert first.start_seconds == 0
    assert first.leading_gap_seconds == 0
    assert first.segment_count >= 5
    assert first.hook_text.startswith("이야기 1 계속")


def test_short_range_yields_single_whole_range_candidate() -> None:
    segments = [
        TranscriptSegment(start_seconds=2, end_seconds=5, text="All right"),
        TranscriptSegment(start_seconds=5, end_seconds=12, text="here we are."),
    ]
    transcript = _transcript(segments, start=2, end=12, language="en")

    result = HeuristicCandidateGenerator().generate(transcript)

    assert len(result.items) == 1
    only = result.items[0]
    assert only.start_seconds == 2
    assert only.end_seconds == 12
    assert only.transcript_text == "All right here we are."
    assert only.ends_on_sentence_boundary is True


def test_candidates_never_exceed_the_requested_range() -> None:
    transcript = _transcript(_speech(30, 95), start=30, end=95)

    result = HeuristicCandidateGenerator().generate(transcript)

    assert result.items
    for item in result.items:
        assert item.start_seconds >= 30
        assert item.end_seconds <= 95
        assert item.duration_seconds <= 60


def test_english_punctuation_marks_sentence_boundaries() -> None:
    segments = []
    cursor = 0.0
    for index in range(40):
        text = f"Sentence number {index} ends here." if index % 3 == 2 else f"clause {index}"
        segments.append(
            TranscriptSegment(start_seconds=cursor, end_seconds=cursor + 4, text=text)
        )
        cursor += 4
    transcript = _transcript(segments, start=0, end=160, language="en")

    result = HeuristicCandidateGenerator().generate(transcript)

    assert all(
        item.starts_on_sentence_boundary or not item.index == 1 for item in result.items
    )
    boundary_ending = [item for item in result.items if item.ends_on_sentence_boundary]
    assert boundary_ending


def test_empty_transcript_text_raises_non_retryable_error() -> None:
    transcript = _transcript(
        [TranscriptSegment(start_seconds=0, end_seconds=1, text=" ")], start=0, end=60
    )

    with pytest.raises(CandidateGenerationError) as excinfo:
        HeuristicCandidateGenerator().generate(transcript)

    assert excinfo.value.retryable is False


def test_generator_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError):
        HeuristicCandidateGenerator(min_seconds=60, max_seconds=30)
    with pytest.raises(ValueError):
        HeuristicCandidateGenerator(target_count_min=5, target_count_max=3)
