from enum import Enum


class RenderTemplate(str, Enum):
    """Caption presets carried from selection to rendering.

    Styles live in ``app/captions.py``. Every value stays valid so stored jobs keep
    loading; ``CaptionStyle.listed`` decides what the picker shows.
    """

    # Headline compositions (2026-10-01): big title with a coloured keyword on top,
    # the source frame in the middle, a small spoken caption at the bottom.
    HEADLINE_YELLOW = "HEADLINE_YELLOW"
    HEADLINE_RED = "HEADLINE_RED"
    HEADLINE_LIME = "HEADLINE_LIME"
    HEADLINE_SKY = "HEADLINE_SKY"
    HEADLINE_BOX = "HEADLINE_BOX"
    # Karaoke captions: the spoken word changes colour.
    IMPACT_YELLOW = "IMPACT_YELLOW"
    KARAOKE_POP = "KARAOKE_POP"
    # Original MVP presets.
    CLEAN_CAPTION = "CLEAN_CAPTION"
    BOLD_HIGHLIGHT = "BOLD_HIGHLIGHT"
    MINIMAL = "MINIMAL"
    # Kept for jobs that used them; no longer listed in the picker.
    NEWS_BAR = "NEWS_BAR"
    NEON_GLOW = "NEON_GLOW"
    HANDWRITING = "HANDWRITING"
    TYPEWRITER = "TYPEWRITER"


class RenderLayout(str, Enum):
    """How a 16:9 source is placed in the 9:16 frame."""

    STAGE = "STAGE"  # whole frame centred on black bands (room for a headline and caption)
    FIT = "FIT"  # whole frame over a blurred copy of itself
    FILL = "FILL"  # scale to cover and center-crop (may cut the sides of the source)
