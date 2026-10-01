from app.range_recommendation import (
    compact_chapters,
    compact_heatmap,
    recommend_ranges,
    youtube_insights,
)


def _heatmap(duration: float, peaks: dict[int, float]) -> list[dict[str, float]]:
    """100 buckets; ``peaks`` maps a bucket index to its intensity (others 0.05)."""
    step = duration / 100
    return compact_heatmap(
        [
            {"start_time": i * step, "end_time": (i + 1) * step, "value": peaks.get(i, 0.05)}
            for i in range(100)
        ]
    )


def test_compact_heatmap_normalises_and_drops_junk() -> None:
    rows = compact_heatmap(
        [
            {"start_time": 10, "end_time": 5, "value": 0.5},  # inverted
            {"start_time": 0, "end_time": 6, "value": 1.7},  # clamped
            "garbage",
            {"start_time": 6, "end_time": 12, "value": 0.25},
        ]
    )
    assert rows == [
        {"start_seconds": 0, "end_seconds": 6, "value": 1.0},
        {"start_seconds": 6, "end_seconds": 12, "value": 0.25},
    ]


def test_compact_chapters_fills_missing_ends_and_clamps_to_duration() -> None:
    rows = compact_chapters(
        [
            {"start_time": 0, "title": "  Intro  "},
            {"start_time": 90, "title": "Main"},
            {"start_time": 500, "title": "After the end"},
        ],
        duration_seconds=400,
    )
    assert rows == [
        {"start_seconds": 0, "end_seconds": 90, "title": "Intro"},
        {"start_seconds": 90, "end_seconds": 400, "title": "Main"},
    ]


def test_recommend_ranges_centres_windows_on_distinct_peaks() -> None:
    duration = 1800.0  # 30 min, 18 s buckets
    heatmap = _heatmap(duration, {50: 1.0, 51: 0.9, 10: 0.7, 90: 0.6})

    ranges = recommend_ranges(heatmap, duration_seconds=duration)

    assert len(ranges) == 3
    assert ranges[0]["score"] == 1.0
    assert ranges[0]["start_seconds"] <= 909 <= ranges[0]["end_seconds"]
    assert all(r["end_seconds"] - r["start_seconds"] == 300 for r in ranges)
    # Bucket 51 is skipped: its window overlaps the first one almost entirely.
    starts = sorted(r["start_seconds"] for r in ranges)
    assert starts[1] - starts[0] >= 210 and starts[2] - starts[1] >= 210
    assert ranges[0]["reason"] == "다시보기가 많은 구간"


def test_recommend_ranges_clamps_to_the_video_edges() -> None:
    duration = 1200.0
    ranges = recommend_ranges(_heatmap(duration, {0: 1.0, 99: 0.9}), duration_seconds=duration, count=2)

    assert ranges[0]["start_seconds"] == 0 and ranges[0]["end_seconds"] == 300
    assert ranges[1]["start_seconds"] == 900 and ranges[1]["end_seconds"] == 1200


def test_recommend_ranges_snaps_to_a_reasonable_chapter() -> None:
    duration = 1800.0
    chapters = compact_chapters(
        [
            {"start_time": 0, "title": "Intro"},
            {"start_time": 800, "title": "핵심 비법"},
            {"start_time": 1000, "title": "마무리"},
        ],
        duration_seconds=duration,
    )
    ranges = recommend_ranges(
        _heatmap(duration, {50: 1.0}), duration_seconds=duration, chapters=chapters, count=1
    )

    assert ranges[0]["start_seconds"] == 800 and ranges[0]["end_seconds"] == 1000
    assert ranges[0]["reason"] == "챕터 「핵심 비법」"

    # A chapter too long for analysis (0-800 s) is ignored in favour of the window.
    ranges = recommend_ranges(
        _heatmap(duration, {20: 1.0}), duration_seconds=duration, chapters=chapters, count=1
    )
    assert ranges[0]["end_seconds"] - ranges[0]["start_seconds"] == 300


def test_recommend_ranges_is_empty_without_data_or_for_short_videos() -> None:
    assert recommend_ranges([], duration_seconds=1800) == []
    assert recommend_ranges(_heatmap(400, {50: 1.0}), duration_seconds=400) == []
    assert recommend_ranges(_heatmap(1800, {}), duration_seconds=1800)  # flat but non-zero still ranks


def test_youtube_insights_reads_yt_dlp_fields() -> None:
    insights = youtube_insights({"heatmap": None, "chapters": None}, duration_seconds=900)
    assert insights == {"heatmap": [], "chapters": [], "recommended_ranges": []}
