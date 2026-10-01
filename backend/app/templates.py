from enum import Enum

# Reserved source-picture band within a 1080 x 1920 STAGE composition.
STAGE_PICTURE_HEIGHT = 608


class RenderTemplate(str, Enum):
    """Caption presets carried from selection to rendering.

    Styles live in ``app/captions.py``. Every value stays valid so stored jobs keep
    loading; ``CaptionStyle.listed`` decides what the picker shows.
    """

    # Compositions (2026-10-01, third pass): a dark or paper "stage" with a headline,
    # the whole source frame, a channel line, and a caption styled per template.
    CAPTION_POP = "CAPTION_POP"
    CAPTION_ACCENT = "CAPTION_ACCENT"
    DARK_MINIMAL = "DARK_MINIMAL"
    PAPER = "PAPER"
    SNS_CARD = "SNS_CARD"
    COMMUNITY = "COMMUNITY"
    # Earlier headline presets and the original MVP presets; unlisted but valid.
    HEADLINE_YELLOW = "HEADLINE_YELLOW"
    HEADLINE_RED = "HEADLINE_RED"
    HEADLINE_LIME = "HEADLINE_LIME"
    HEADLINE_SKY = "HEADLINE_SKY"
    HEADLINE_BOX = "HEADLINE_BOX"
    IMPACT_YELLOW = "IMPACT_YELLOW"
    KARAOKE_POP = "KARAOKE_POP"
    CLEAN_CAPTION = "CLEAN_CAPTION"
    BOLD_HIGHLIGHT = "BOLD_HIGHLIGHT"
    MINIMAL = "MINIMAL"
    NEWS_BAR = "NEWS_BAR"
    NEON_GLOW = "NEON_GLOW"
    HANDWRITING = "HANDWRITING"
    TYPEWRITER = "TYPEWRITER"


class RenderLayout(str, Enum):
    """How a 16:9 source is placed in the 9:16 frame."""

    STAGE = "STAGE"  # whole frame centred on the template's stage colour (room for a headline)
    FIT = "FIT"  # whole frame over a blurred copy of itself
    FILL = "FILL"  # scale to cover and center-crop (may cut the sides of the source)


class CaptionPosition(str, Enum):
    """Where spoken captions go."""

    BOTTOM = "BOTTOM"  # under the picture (or near the bottom on FILL)
    MIDDLE = "MIDDLE"  # over the centre of the picture
