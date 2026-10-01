"""Suggest analysis ranges from YouTube's "most replayed" heatmap and chapters.

The watch page exposes a 100-bucket replay-intensity curve for videos with enough
views, and yt-dlp (which Apify Titan's metadata file mirrors) surfaces it as
``heatmap`` next to ``chapters``. Neither is a Shorts signal on its own: this module
turns them into a few analysis windows the creator can accept with one click, and
the AI still picks the Top 3 inside whatever window they settle on.
"""

from typing import Any


# An analysis window around a replay peak: long enough for 10+ candidates, short
# enough that the peak still dominates what the ranker sees.
DEFAULT_WINDOW_SECONDS = 300.0
# Videos at most this much longer than the window gain nothing from a suggestion.
MIN_VIDEO_SECONDS_FOR_RECOMMENDATION = DEFAULT_WINDOW_SECONDS * 1.5
MAX_RECOMMENDATIONS = 3
MAX_OVERLAP_RATIO = 0.3
# A chapter replaces the fixed window when its length is reasonable for analysis.
MIN_CHAPTER_SECONDS = 60.0
MAX_CHAPTER_SECONDS = 600.0


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def compact_heatmap(raw: Any) -> list[dict[str, float]]:
    """Normalise yt-dlp heatmap entries to {start_seconds, end_seconds, value} rows."""
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, float]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        start = _number(entry.get("start_time", entry.get("start_seconds")))
        end = _number(entry.get("end_time", entry.get("end_seconds")))
        value = _number(entry.get("value"))
        if start is None or end is None or value is None or end <= start:
            continue
        rows.append(
            {
                "start_seconds": round(start, 2),
                "end_seconds": round(end, 2),
                "value": round(max(0.0, min(1.0, value)), 4),
            }
        )
    rows.sort(key=lambda row: row["start_seconds"])
    return rows


def compact_chapters(raw: Any, *, duration_seconds: float) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        start = _number(entry.get("start_time", entry.get("start_seconds")))
        if start is None or start < 0 or start >= duration_seconds:
            continue
        end = _number(entry.get("end_time", entry.get("end_seconds")))
        if end is None:
            following = raw[index + 1] if index + 1 < len(raw) else None
            end = _number(following.get("start_time")) if isinstance(following, dict) else None
        end = min(duration_seconds, end if end is not None else duration_seconds)
        if end <= start:
            continue
        title = entry.get("title")
        rows.append(
            {
                "start_seconds": round(start, 2),
                "end_seconds": round(end, 2),
                "title": " ".join(title.split())[:80] if isinstance(title, str) else None,
            }
        )
    rows.sort(key=lambda row: row["start_seconds"])
    return rows


def _window_score(heatmap: list[dict[str, float]], start: float, end: float) -> float:
    """Replay intensity inside [start, end], weighting partially covered buckets."""
    score = 0.0
    for row in heatmap:
        overlap = min(end, row["end_seconds"]) - max(start, row["start_seconds"])
        if overlap > 0:
            score += row["value"] * overlap
    return score


def _overlap_ratio(a: tuple[float, float], b: tuple[float, float]) -> float:
    overlap = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    shorter = min(a[1] - a[0], b[1] - b[0])
    return overlap / shorter if shorter > 0 else 1.0


def _chapter_around(
    chapters: list[dict[str, Any]], peak_seconds: float
) -> dict[str, Any] | None:
    for chapter in chapters:
        if chapter["start_seconds"] <= peak_seconds < chapter["end_seconds"]:
            length = chapter["end_seconds"] - chapter["start_seconds"]
            if MIN_CHAPTER_SECONDS <= length <= MAX_CHAPTER_SECONDS:
                return chapter
            return None
    return None


def recommend_ranges(
    heatmap: list[dict[str, float]],
    *,
    duration_seconds: float,
    chapters: list[dict[str, Any]] | None = None,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
    count: int = MAX_RECOMMENDATIONS,
) -> list[dict[str, Any]]:
    """Up to ``count`` distinct analysis windows, best replay intensity first.

    Each window is centred on a replay peak and snapped to the chapter containing
    that peak when the chapter is a sensible analysis length. Scores are relative
    to the best window (1.0) so the UI can show them as a simple bar.
    """
    if not heatmap or duration_seconds < MIN_VIDEO_SECONDS_FOR_RECOMMENDATION:
        return []
    window = min(window_seconds, duration_seconds)
    chapters = chapters or []
    # Peak = bucket with the highest intensity; buckets are the natural step size.
    ordered_buckets = sorted(heatmap, key=lambda row: -row["value"])
    picked: list[dict[str, Any]] = []
    for bucket in ordered_buckets:
        if len(picked) >= count:
            break
        if bucket["value"] <= 0:
            break
        peak = (bucket["start_seconds"] + bucket["end_seconds"]) / 2
        chapter = _chapter_around(chapters, peak)
        if chapter is not None:
            start, end = chapter["start_seconds"], chapter["end_seconds"]
            reason = f"챕터 「{chapter['title']}」" if chapter.get("title") else "챕터 구간"
        else:
            start = max(0.0, min(peak - window / 2, duration_seconds - window))
            end = min(duration_seconds, start + window)
            reason = "다시보기가 많은 구간"
        if any(_overlap_ratio((start, end), (p["start_seconds"], p["end_seconds"])) > MAX_OVERLAP_RATIO for p in picked):
            continue
        picked.append(
            {
                "start_seconds": round(start),
                "end_seconds": round(end),
                "peak_seconds": round(peak),
                "score": _window_score(heatmap, start, end) / max(end - start, 1.0),
                "reason": reason,
            }
        )
    if not picked:
        return []
    best = max(item["score"] for item in picked) or 1.0
    for item in picked:
        item["score"] = round(item["score"] / best, 3)
    picked.sort(key=lambda item: -item["score"])
    return picked


def youtube_insights(info: dict[str, Any], *, duration_seconds: float) -> dict[str, Any]:
    """Metadata fields derived from a yt-dlp info dict: heatmap, chapters, suggestions."""
    heatmap = compact_heatmap(info.get("heatmap"))
    chapters = compact_chapters(info.get("chapters"), duration_seconds=duration_seconds)
    return {
        "heatmap": heatmap,
        "chapters": chapters,
        "recommended_ranges": recommend_ranges(
            heatmap, duration_seconds=duration_seconds, chapters=chapters
        ),
    }
