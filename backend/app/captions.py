"""Caption rendering: transcript cues (and an optional headline) -> ASS file.

Templates differ only in ASS style values; karaoke presets emit one event per
spoken word so the current word is coloured, and every preset can draw a headline
(title with one coloured keyword) when the render has a title. FFmpeg burns the
file with the ``subtitles`` filter (libass); no template logic lives in the video
code.
"""

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.templates import RenderLayout, RenderTemplate


PLAY_RES_X = 1080
PLAY_RES_Y = 1920
MIN_CUE_SECONDS = 0.3
# A 16:9 source placed whole in the 9:16 frame is 1080x607, centred: y 656..1263.
PICTURE_TOP = 656
PICTURE_BOTTOM = 1263
# Captions in the band under the picture (bottom edge at 1920-440 = 1480).
BAND_CAPTION_MARGIN_V = 440
# Headline centred in the band above the picture; overlaid near the top on FILL.
BAND_HEADLINE_Y = PICTURE_TOP // 2
FILL_HEADLINE_Y = 230
HEADLINE_MARGIN_X = 70
MAX_TITLE_CHARS = 80


class CaptionWord(BaseModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    text: str = Field(min_length=1)


class CaptionCue(BaseModel):
    """Absolute source-video times; converted to clip-relative when the file is built."""

    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    text: str = Field(min_length=1)
    words: list[CaptionWord] | None = None


@dataclass(frozen=True)
class CaptionStyle:
    name: str
    description: str
    tag: str
    font_name: str
    font_size: int
    primary: str  # ASS &HAABBGGRR
    outline: str
    back: str
    bold: int
    border_style: int  # 1 = outline + shadow, 3 = opaque box
    outline_width: int
    shadow: int
    margin_v: int
    alignment: int = 2  # 2 bottom-centre, 5 middle-centre, 8 top-centre
    italic: int = 0
    spacing: int = 0
    blur: float = 0.0
    highlight: str | None = None  # karaoke: colour of the word being spoken
    bar_height: int = 0  # >0 draws a full-width band behind each cue (news lower third)
    # Headline (title) drawn when the render has one.
    headline_accent: str = "&H0000E6FF"
    headline_font: str = "NanumSquareRound"
    headline_size: int = 84
    headline_box: bool = False
    listed: bool = True
    # CSS-ish hints for the picker preview; the frontend uses them, the renderer does not.
    preview: dict[str, str] | None = None


WHITE = "&H00FFFFFF"
BLACK = "&H00000000"
ACCENT = "&H004FFFD7"  # #D7FF4F
YELLOW = "&H0000E6FF"  # #FFE600
RED = "&H003C3CFF"  # #FF3C3C
SKY = "&H00FFD24F"  # #4FD2FF
MAGENTA = "&H00FF4FD7"  # #D74FFF
CYAN = "&H00FFE14F"  # #4FE1FF


def _headline_template(
    *,
    name: str,
    description: str,
    accent: str,
    accent_css: str,
    box: bool = False,
    caption_box: bool = False,
) -> CaptionStyle:
    """The composition in today's Korean Shorts: headline on top, small caption below."""
    preview = {
        "color": "#FFFFFF",
        "stroke": "#000000",
        "weight": "800",
        "headlineAccent": accent_css,
        "headlineBox": "true" if box else "false",
    }
    if caption_box:
        preview["background"] = "#000000"
    return CaptionStyle(
        name=name,
        description=description,
        tag="요즘 감성",
        font_name="NanumSquareRound",
        font_size=50,
        primary=WHITE,
        outline=BLACK,
        back="&HA0000000" if caption_box else "&H80000000",
        bold=-1,
        border_style=3 if caption_box else 1,
        outline_width=12 if caption_box else 3,
        shadow=0,
        margin_v=260,
        headline_accent=accent,
        headline_box=box,
        preview=preview,
    )


TEMPLATE_STYLES: dict[RenderTemplate, CaptionStyle] = {
    RenderTemplate.HEADLINE_YELLOW: _headline_template(
        name="헤드라인 옐로",
        description="큰 제목에 노란 키워드, 아래에 작은 자막. 요즘 쇼츠의 기본형.",
        accent=YELLOW,
        accent_css="#FFE600",
    ),
    RenderTemplate.HEADLINE_RED: _headline_template(
        name="헤드라인 레드",
        description="빨간 키워드로 긴장감을 주는 제목. 다큐·이슈 영상에.",
        accent=RED,
        accent_css="#FF3C3C",
    ),
    RenderTemplate.HEADLINE_LIME: _headline_template(
        name="헤드라인 라임",
        description="형광 연두 키워드. 정보·꿀팁 영상에 잘 맞아요.",
        accent=ACCENT,
        accent_css="#D7FF4F",
    ),
    RenderTemplate.HEADLINE_SKY: _headline_template(
        name="헤드라인 뉴스",
        description="하늘색 키워드와 박스 자막. 뉴스·시사 느낌.",
        accent=SKY,
        accent_css="#4FD2FF",
        caption_box=True,
    ),
    RenderTemplate.HEADLINE_BOX: _headline_template(
        name="헤드라인 박스",
        description="제목을 검은 박스 위에 얹어 어떤 배경에서도 또렷하게.",
        accent=YELLOW,
        accent_css="#FFE600",
        box=True,
    ),
    RenderTemplate.IMPACT_YELLOW: CaptionStyle(
        name="임팩트 옐로",
        description="두꺼운 자막, 말하는 단어만 노란색으로 바뀌어요.",
        tag="단어 강조",
        font_name="NanumSquareRound",
        font_size=74,
        primary=WHITE,
        outline=BLACK,
        back="&H00000000",
        bold=-1,
        border_style=1,
        outline_width=7,
        shadow=2,
        margin_v=0,
        alignment=5,
        spacing=1,
        highlight=YELLOW,
        headline_accent=YELLOW,
        preview={
            "color": "#FFFFFF",
            "stroke": "#000000",
            "accent": "#FFE600",
            "weight": "900",
            "headlineAccent": "#FFE600",
        },
    ),
    RenderTemplate.KARAOKE_POP: CaptionStyle(
        name="카라오케 팝",
        description="검은 박스 위 흰 글씨, 말하는 단어만 형광색으로.",
        tag="단어 강조",
        font_name="NanumSquareRound",
        font_size=70,
        primary=WHITE,
        outline=BLACK,
        back="&H90000000",
        bold=-1,
        border_style=3,
        outline_width=14,
        shadow=0,
        margin_v=420,
        highlight=ACCENT,
        headline_accent=ACCENT,
        preview={
            "color": "#FFFFFF",
            "background": "#111111",
            "accent": "#D7FF4F",
            "weight": "900",
            "headlineAccent": "#D7FF4F",
        },
    ),
    RenderTemplate.CLEAN_CAPTION: CaptionStyle(
        name="클린",
        description="읽기 쉬운 기본 자막. 흰 글씨에 검은 외곽선.",
        tag="기본",
        font_name="NanumGothic",
        font_size=64,
        primary=WHITE,
        outline=BLACK,
        back="&H80000000",
        bold=-1,
        border_style=1,
        outline_width=4,
        shadow=1,
        margin_v=300,
        preview={"color": "#FFFFFF", "stroke": "#000000", "weight": "700", "headlineAccent": "#FFE600"},
    ),
    RenderTemplate.BOLD_HIGHLIGHT: CaptionStyle(
        name="볼드 박스",
        description="형광 글씨를 검은 박스 위에. 핵심 문장을 강하게.",
        tag="기본",
        font_name="NanumGothic",
        font_size=80,
        primary=ACCENT,
        outline=BLACK,
        back="&H70000000",
        bold=-1,
        border_style=3,
        outline_width=16,
        shadow=0,
        margin_v=520,
        headline_accent=ACCENT,
        preview={"color": "#D7FF4F", "background": "#111111", "weight": "800", "headlineAccent": "#D7FF4F"},
    ),
    RenderTemplate.MINIMAL: CaptionStyle(
        name="미니멀",
        description="화면을 가리지 않는 작은 자막.",
        tag="기본",
        font_name="NanumGothic",
        font_size=48,
        primary=WHITE,
        outline=BLACK,
        back=BLACK,
        bold=0,
        border_style=1,
        outline_width=2,
        shadow=0,
        margin_v=180,
        headline_accent=WHITE,
        preview={"color": "#FFFFFF", "stroke": "#000000", "weight": "400", "headlineAccent": "#FFFFFF"},
    ),
    RenderTemplate.NEWS_BAR: CaptionStyle(
        name="News Bar",
        description="뉴스 하단 자막처럼 가로 띠 위에 또렷하게.",
        tag="정보",
        font_name="NanumBarunGothic",
        font_size=58,
        primary=WHITE,
        outline="&H00202020",
        back="&HB0202020",
        bold=-1,
        border_style=1,
        outline_width=0,
        shadow=0,
        margin_v=240,
        bar_height=130,
        headline_accent=SKY,
        listed=False,
        preview={"color": "#FFFFFF", "background": "#202020", "weight": "700"},
    ),
    RenderTemplate.NEON_GLOW: CaptionStyle(
        name="Neon Glow",
        description="어두운 영상 위에 빛나는 네온 글씨.",
        tag="감성",
        font_name="NanumSquare",
        font_size=72,
        primary=CYAN,
        outline=MAGENTA,
        back="&H60000000",
        bold=-1,
        border_style=1,
        outline_width=4,
        shadow=3,
        margin_v=360,
        blur=6.0,
        headline_accent=CYAN,
        listed=False,
        preview={"color": "#4FE1FF", "stroke": "#D74FFF", "weight": "800", "glow": "true"},
    ),
    RenderTemplate.HANDWRITING: CaptionStyle(
        name="Handwriting",
        description="손글씨 느낌의 따뜻한 자막. 브이로그와 감성 영상에.",
        tag="감성",
        font_name="Nanum Pen Script",
        font_size=92,
        primary=WHITE,
        outline="&H00303030",
        back="&H00000000",
        bold=0,
        border_style=1,
        outline_width=3,
        shadow=2,
        margin_v=320,
        headline_font="Nanum Pen Script",
        headline_size=96,
        listed=False,
        preview={"color": "#FFFFFF", "stroke": "#303030", "weight": "400", "font": "cursive"},
    ),
    RenderTemplate.TYPEWRITER: CaptionStyle(
        name="Typewriter",
        description="고정폭 글씨와 검은 박스. 설명·튜토리얼 영상에.",
        tag="정보",
        font_name="NanumGothicCoding",
        font_size=56,
        primary=ACCENT,
        outline=BLACK,
        back="&HC0000000",
        bold=-1,
        border_style=3,
        outline_width=12,
        shadow=0,
        margin_v=300,
        spacing=2,
        headline_font="NanumGothicCoding",
        headline_accent=ACCENT,
        listed=False,
        preview={"color": "#D7FF4F", "background": "#000000", "weight": "700", "font": "monospace"},
    ),
}


def template_catalog() -> list[dict[str, Any]]:
    """What the picker needs for listed templates: id, names, tag, preview hints, flags."""
    return [
        {
            "id": template.value,
            "name": style.name,
            "description": style.description,
            "tag": style.tag,
            "karaoke": style.highlight is not None,
            "preview": style.preview or {},
        }
        for template, style in TEMPLATE_STYLES.items()
        if style.listed
    ]


def layout_catalog() -> list[dict[str, str]]:
    return [
        {
            "id": RenderLayout.STAGE.value,
            "name": "제목 + 원본",
            "description": "검은 배경 가운데에 원본 화면을 그대로 두고, 위에는 제목, 아래에는 자막을 넣습니다.",
        },
        {
            "id": RenderLayout.FIT.value,
            "name": "원본 + 흐린 배경",
            "description": "원본 화면을 전부 보여 주고 위아래는 흐린 배경으로 채웁니다.",
        },
        {
            "id": RenderLayout.FILL.value,
            "name": "가득 채우기",
            "description": "화면을 꽉 채우고 양옆을 잘라냅니다. 인물 중심 영상에 좋아요.",
        },
    ]


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


_BRACKET = re.compile(r"\[([^\[\]]+)\]")


def headline_keyword(title: str) -> str | None:
    """The word to colour: a ``[bracketed]`` phrase if the user marked one, else the longest word."""
    marked = _BRACKET.search(title)
    if marked:
        return marked.group(1).strip() or None
    words = [w for w in re.split(r"\s+", title.strip()) if len(w) >= 2]
    if len(words) < 2:
        return None
    return max(words, key=len)


def _headline_text(title: str, accent: str) -> str:
    """ASS text for the headline: user line breaks kept, keyword recoloured."""
    keyword = headline_keyword(title)
    lines = [" ".join(line.split()) for line in title.replace("\r", "").split("\n")]
    plain = "\\N".join(re.sub(r"[{}]", "", line) for line in lines if line)
    plain = plain.replace("[", "").replace("]", "")
    if not keyword:
        return plain
    coloured = f"{{\\1c{accent}}}{keyword}{{\\1c{WHITE}}}"
    return plain.replace(keyword, coloured, 1)


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
        words = None
        if cue.words:
            words = [
                CaptionWord(
                    start_seconds=max(w.start_seconds, start),
                    end_seconds=min(w.end_seconds, end),
                    text=w.text,
                )
                for w in cue.words
                if w.end_seconds > start and w.start_seconds < end
            ]
            words = [w for w in words if w.end_seconds > w.start_seconds] or None
        selected.append(CaptionCue(start_seconds=start, end_seconds=end, text=cue.text, words=words))
    return selected


def _style_line(name: str, style: CaptionStyle, *, alignment: int, margin_v: int) -> str:
    return (
        f"Style: {name},{style.font_name},{style.font_size},{style.primary},&H000000FF,"
        f"{style.outline},{style.back},{style.bold},{style.italic},0,0,100,100,{style.spacing},0,"
        f"{style.border_style},{style.outline_width},{style.shadow},{alignment},90,90,{margin_v},1"
    )


def _headline_style_line(style: CaptionStyle) -> str:
    border_style, outline, back = (
        (3, 18, "&H90000000") if style.headline_box else (1, 5, "&H80000000")
    )
    return (
        f"Style: Headline,{style.headline_font},{style.headline_size},{WHITE},&H000000FF,"
        f"{BLACK},{back},-1,0,0,0,100,100,0,0,{border_style},{outline},0,5,"
        f"{HEADLINE_MARGIN_X},{HEADLINE_MARGIN_X},0,1"
    )


def _header(
    style: CaptionStyle, *, layout: RenderLayout
) -> tuple[list[str], str, int]:
    """ASS header, the global override prefix (blur) for every event, and the MarginV used."""
    if layout in (RenderLayout.FIT, RenderLayout.STAGE):
        alignment, margin_v = 2, BAND_CAPTION_MARGIN_V
    else:
        alignment, margin_v = style.alignment, style.margin_v
    lines = [
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
        _style_line("Default", style, alignment=alignment, margin_v=margin_v),
        _headline_style_line(style),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    prefix = f"{{\\blur{style.blur:g}}}" if style.blur else ""
    return lines, prefix, margin_v


def _headline_event(
    style: CaptionStyle, *, title: str, end: float, layout: RenderLayout
) -> str:
    y = FILL_HEADLINE_Y if layout == RenderLayout.FILL else BAND_HEADLINE_Y
    text = _headline_text(title, style.headline_accent)
    return (
        f"Dialogue: 2,{_ass_time(0)},{_ass_time(end)},Headline,,0,0,0,,"
        f"{{\\an5\\pos({PLAY_RES_X // 2},{y})}}{text}"
    )


def _bar_event(style: CaptionStyle, *, start: float, end: float, margin_v: int) -> str:
    """Full-width translucent band behind a bottom-aligned cue (news lower third)."""
    # Text bottom sits at PlayResY - MarginV; centre the band on the text's middle.
    centre = PLAY_RES_Y - margin_v - style.font_size // 2
    top = centre - style.bar_height // 2
    return (
        f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,"
        f"{{\\an7\\pos(0,{top})\\1c&H{style.back[4:]}&\\1a&H30&\\bord0\\shad0\\p1}}"
        f"m 0 0 l {PLAY_RES_X} 0 l {PLAY_RES_X} {style.bar_height} l 0 {style.bar_height}{{\\p0}}"
    )


def _karaoke_events(
    cue: CaptionCue, style: CaptionStyle, *, offset: float, prefix: str
) -> list[str]:
    """One event per word: the whole line stays visible, the current word is coloured."""
    assert cue.words and style.highlight
    words = cue.words
    events: list[str] = []
    for index, word in enumerate(words):
        start = word.start_seconds - offset
        end = (words[index + 1].start_seconds if index + 1 < len(words) else cue.end_seconds) - offset
        if end <= start:
            continue
        parts = []
        for j, other in enumerate(words):
            text = _ass_text(other.text)
            if j == index:
                # Only the fill colour changes: libass 0.17 renders \3c/\bord combos
                # mid-line as a blurred halo, so boxes stay a style-level BorderStyle 3.
                parts.append(f"{{\\1c{style.highlight}}}{text}{{\\r}}")
            else:
                parts.append(text)
        events.append(
            f"Dialogue: 1,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{prefix}{' '.join(parts)}"
        )
    return events


def build_ass(
    cues: list[CaptionCue],
    *,
    template: RenderTemplate,
    clip_start_seconds: float,
    clip_end_seconds: float,
    layout: RenderLayout = RenderLayout.FILL,
    title: str | None = None,
) -> str:
    """Return an ASS document whose times are relative to the clip start."""
    style = TEMPLATE_STYLES[template]
    lines, prefix, margin_v = _header(style, layout=layout)
    if title and title.strip():
        lines.append(
            _headline_event(
                style,
                title=title.strip()[:MAX_TITLE_CHARS],
                end=clip_end_seconds - clip_start_seconds,
                layout=layout,
            )
        )
    for cue in select_cues(cues, start_seconds=clip_start_seconds, end_seconds=clip_end_seconds):
        if style.bar_height:
            lines.append(
                _bar_event(
                    style,
                    start=cue.start_seconds - clip_start_seconds,
                    end=cue.end_seconds - clip_start_seconds,
                    margin_v=margin_v,
                )
            )
        if style.highlight and cue.words and len(cue.words) > 1:
            lines.extend(_karaoke_events(cue, style, offset=clip_start_seconds, prefix=prefix))
            continue
        text = _ass_text(cue.text)
        if not text:
            continue
        start = cue.start_seconds - clip_start_seconds
        end = cue.end_seconds - clip_start_seconds
        lines.append(f"Dialogue: 1,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{prefix}{text}")
    return "\n".join(lines) + "\n"


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
    speech_alignment = 2
    speech_margin = 560
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
            _style_line("Speech", style, alignment=speech_alignment, margin_v=speech_margin),
            "Style: Title,NanumGothic,56,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,"
            "100,100,0,0,3,14,0,8,80,80,120,1",
            "Style: Price,NanumGothic,68,&H004FFFD7,&H000000FF,&H00000000,&H90000000,-1,0,0,0,"
            "100,100,0,0,3,14,0,8,80,80,260,1",
            "Style: Cta,NanumGothic,48,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,"
            "100,100,0,0,3,12,0,2,80,80,150,1",
            "Style: Disclosure,NanumGothic,30,&H00DDDDDD,&H000000FF,&H00000000,&H90000000,0,0,0,0,"
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
    lines.append(f"Dialogue: 0,{_ass_time(0)},{end},Disclosure,,0,0,0,,{_ass_text(disclosure)}")
    prefix = f"{{\\blur{style.blur:g}}}" if style.blur else ""
    for cue in select_cues(cues, start_seconds=0, end_seconds=total_seconds):
        text = _ass_text(cue.text)
        if text:
            lines.append(
                f"Dialogue: 1,{_ass_time(cue.start_seconds)},{_ass_time(cue.end_seconds)},"
                f"Speech,,0,0,0,,{prefix}{text}"
            )
    return "\n".join(lines) + "\n"
