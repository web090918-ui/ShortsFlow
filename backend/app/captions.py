"""Task 08 caption rendering: transcript cues -> ASS subtitle file per template.

The three MVP templates differ only in ASS style values. FFmpeg burns the file in
with the ``subtitles`` filter (libass); no template logic lives in the video code.
"""

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.downloads import RenderTemplate


PLAY_RES_X = 1080
PLAY_RES_Y = 1920
FONT_NAME = "NanumGothic"
MIN_CUE_SECONDS = 0.3


class CaptionCue(BaseModel):
    """Absolute source-video times; converted to clip-relative when the file is built."""

    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    text: str = Field(min_length=1)


@dataclass(frozen=True)
class _Style:
    font_size: int
    primary: str  # ASS &HAABBGGRR
    outline: str
    back: str
    bold: int
    border_style: int  # 1 = outline + shadow, 3 = opaque box
    outline_width: int
    shadow: int
    margin_v: int
    alignment: int = 2  # bottom-center


# Accent #D7FF4F -> ASS BBGGRR = 4FFFD7.
TEMPLATE_STYLES: dict[RenderTemplate, _Style] = {
    RenderTemplate.CLEAN_CAPTION: _Style(
        font_size=64,
        primary="&H00FFFFFF",
        outline="&H00000000",
        back="&H80000000",
        bold=-1,
        border_style=1,
        outline_width=4,
        shadow=1,
        margin_v=300,
    ),
    RenderTemplate.BOLD_HIGHLIGHT: _Style(
        font_size=80,
        primary="&H004FFFD7",
        outline="&H00000000",
        back="&H70000000",
        bold=-1,
        border_style=3,
        outline_width=16,
        shadow=0,
        margin_v=520,
    ),
    RenderTemplate.MINIMAL: _Style(
        font_size=48,
        primary="&H00FFFFFF",
        outline="&H00000000",
        back="&H00000000",
        bold=0,
        border_style=1,
        outline_width=2,
        shadow=0,
        margin_v=180,
    ),
}


def _ass_time(seconds: float) -> str:
    total = max(0.0, seconds)
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = total % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _ass_text(text: str) -> str:
    cleaned = re.sub(r"[{}]", "", text)
    cleaned = " ".join(cleaned.split())
    return cleaned.replace("\n", "\\N")


def select_cues(
    cues: list[CaptionCue], *, start_seconds: float, end_seconds: float
) -> list[CaptionCue]:
    """Keep cues overlapping the clip, clamped to its bounds, one on screen at a time.

    Auto-generated captions often overlap the next cue; showing both stacks two
    boxes on screen, so each cue ends where the next one starts.
    """
    ordered = sorted(cues, key=lambda item: item.start_seconds)
    selected: list[CaptionCue] = []
    for index, cue in enumerate(ordered):
        start = max(cue.start_seconds, start_seconds)
        end = min(cue.end_seconds, end_seconds)
        if index + 1 < len(ordered):
            end = min(end, max(ordered[index + 1].start_seconds, start))
        if end - start < MIN_CUE_SECONDS:
            continue
        selected.append(CaptionCue(start_seconds=start, end_seconds=end, text=cue.text))
    return selected


def build_product_ass(
    cues: list[CaptionCue],
    *,
    template: RenderTemplate,
    total_seconds: float,
    title: str,
    price_line: str | None,
    cta: str,
    disclosure: str,
) -> str:
    """ASS for a product Short: title and price on top, spoken lines in the middle,
    CTA and the affiliate disclosure pinned at the bottom for the whole clip."""
    style = TEMPLATE_STYLES[template]
    header = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {PLAY_RES_X}",
            f"PlayResY: {PLAY_RES_Y}",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
            "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
            "MarginR, MarginV, Encoding",
            # Spoken line: template style, centred a little below the middle.
            f"Style: Speech,{FONT_NAME},{style.font_size},{style.primary},&H000000FF,"
            f"{style.outline},{style.back},{style.bold},0,0,0,100,100,0,0,"
            f"{style.border_style},{style.outline_width},{style.shadow},2,90,90,560,1",
            # Title block at the top: white on a dark box.
            f"Style: Title,{FONT_NAME},56,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,"
            "100,100,0,0,3,14,0,8,80,80,120,1",
            # Price under the title: accent colour.
            f"Style: Price,{FONT_NAME},68,&H004FFFD7,&H000000FF,&H00000000,&H90000000,-1,0,0,0,"
            "100,100,0,0,3,14,0,8,80,80,260,1",
            # CTA above the disclosure.
            f"Style: Cta,{FONT_NAME},48,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,"
            "100,100,0,0,3,12,0,2,80,80,150,1",
            # Disclosure: small, always visible, required by Coupang Partners.
            f"Style: Disclosure,{FONT_NAME},30,&H00DDDDDD,&H000000FF,&H00000000,&H90000000,0,0,0,0,"
            "100,100,0,0,3,8,0,2,60,60,40,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )
    end = _ass_time(total_seconds)
    lines = [
        header,
        f"Dialogue: 0,{_ass_time(0)},{end},Title,,0,0,0,,{_ass_text(title)}",
    ]
    if price_line:
        lines.append(f"Dialogue: 0,{_ass_time(0)},{end},Price,,0,0,0,,{_ass_text(price_line)}")
    lines.append(f"Dialogue: 0,{_ass_time(0)},{end},Cta,,0,0,0,,{_ass_text(cta)}")
    lines.append(
        f"Dialogue: 0,{_ass_time(0)},{end},Disclosure,,0,0,0,,{_ass_text(disclosure)}"
    )
    for cue in select_cues(cues, start_seconds=0, end_seconds=total_seconds):
        text = _ass_text(cue.text)
        if text:
            lines.append(
                f"Dialogue: 1,{_ass_time(cue.start_seconds)},{_ass_time(cue.end_seconds)},"
                f"Speech,,0,0,0,,{text}"
            )
    return "\n".join(lines) + "\n"


def build_ass(
    cues: list[CaptionCue],
    *,
    template: RenderTemplate,
    clip_start_seconds: float,
    clip_end_seconds: float,
) -> str:
    """Return an ASS document whose times are relative to the clip start."""
    style = TEMPLATE_STYLES[template]
    header = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {PLAY_RES_X}",
            f"PlayResY: {PLAY_RES_Y}",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
            "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
            "MarginR, MarginV, Encoding",
            f"Style: Default,{FONT_NAME},{style.font_size},{style.primary},&H000000FF,"
            f"{style.outline},{style.back},{style.bold},0,0,0,100,100,0,0,"
            f"{style.border_style},{style.outline_width},{style.shadow},{style.alignment},"
            f"90,90,{style.margin_v},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )
    lines = [header]
    for cue in select_cues(cues, start_seconds=clip_start_seconds, end_seconds=clip_end_seconds):
        text = _ass_text(cue.text)
        if not text:
            continue
        start = cue.start_seconds - clip_start_seconds
        end = cue.end_seconds - clip_start_seconds
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"
