from enum import Enum


class RenderTemplate(str, Enum):
    """Caption presets carried from selection to rendering.

    The first three are the original MVP presets; the rest were added on
    2026-10-01 to match the styles creators see in Opus, Klap, Vizard, and CapCut.
    Styles themselves live in ``app/captions.py``.
    """

    CLEAN_CAPTION = "CLEAN_CAPTION"
    BOLD_HIGHLIGHT = "BOLD_HIGHLIGHT"
    MINIMAL = "MINIMAL"
    IMPACT_YELLOW = "IMPACT_YELLOW"
    KARAOKE_POP = "KARAOKE_POP"
    NEWS_BAR = "NEWS_BAR"
    NEON_GLOW = "NEON_GLOW"
    HANDWRITING = "HANDWRITING"
    TYPEWRITER = "TYPEWRITER"


class RenderLayout(str, Enum):
    """How a 16:9 source is placed in the 9:16 frame."""

    FILL = "FILL"  # scale to cover and center-crop (may cut the sides of the source)
    FIT = "FIT"  # keep the whole frame, letterboxed over a blurred copy of itself
