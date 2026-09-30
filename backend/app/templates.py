from enum import Enum


class RenderTemplate(str, Enum):
    """The three MVP caption presets carried from selection to rendering."""

    CLEAN_CAPTION = "CLEAN_CAPTION"
    BOLD_HIGHLIGHT = "BOLD_HIGHLIGHT"
    MINIMAL = "MINIMAL"
