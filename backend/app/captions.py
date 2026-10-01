"""Caption rendering: transcript cues, headline, and chrome -> one ASS file.

A template is a composition: a stage colour behind the whole source frame, a
headline (title with a brand-coloured keyword), a channel line, optional chrome
(tag pill, header band, hashtags) and the spoken caption style. Karaoke presets
emit one event per spoken word so the current word is coloured. FFmpeg burns the
file with the ``subtitles`` filter (libass); no template logic lives in the video
code.
"""

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.templates import (
    STAGE_PICTURE_HEIGHT,
    TALL_PICTURE_HEIGHT,
    CaptionPosition,
    RenderLayout,
    RenderTemplate,
)


PLAY_RES_X = 1080
PLAY_RES_Y = 1920
MIN_CUE_SECONDS = 0.3
# Stage geometry depends on the template's picture height; see picture_band().
# The chrome positions below were designed for a 656 px band above a 608 px picture
# and are scaled to the actual band height.
DESIGN_BAND_HEIGHT = 656
FILL_HEADLINE_Y = 230
FILL_CHANNEL_LINE_Y = 1800
# Product Shorts: a taller picture box for square product photos.
PRODUCT_PICTURE_TOP = 330
PRODUCT_PICTURE_BOTTOM = 1230
PRODUCT_HEADLINE_Y = PRODUCT_PICTURE_TOP // 2
HEADLINE_MARGIN_X = 70
MAX_TITLE_CHARS = 100
DEFAULT_BRAND_COLOR = "#4FE1E1"  # aqua, the default swatch in the picker
BRAND = "BRAND"  # sentinel: use the render's brand colour

HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
# Title intro: the headline fills the frame for the first moments, then settles into
# its usual place. Shorts are judged in the first three seconds.
INTRO_SECONDS = 2.4
INTRO_SCALE = 150  # percent of the headline font size


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
    primary: str  # ASS &HAABBGGRR, or BRAND
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
    highlight: str | None = None  # karaoke: colour of the word being spoken (or BRAND)
    emphasize_longest: bool = False  # non-karaoke: colour the longest word of each cue
    bar_height: int = 0  # >0 draws a full-width band behind each cue (news lower third)
    show_caption: bool = True
    positionable: bool = False  # the viewer may move the caption (하단/중앙)
    # Stage and headline.
    stage_color: str = "#000000"  # behind the picture in the STAGE layout; hex
    text_color: str = "&H00FFFFFF"  # headline and chrome text on the stage
    headline_accent: str = BRAND
    headline_font: str = "NanumSquareRound"
    headline_size: int = 84
    headline_box: bool = False
    headline_align_left: bool = False
    channel_line: bool = True
    tagline: str | None = None  # pill above the headline (SNS card)
    header_band: str | None = None  # full-width band at the very top (community)
    kicker: str | None = None  # small brand-coloured line above the headline
    hashtags: bool = False  # draw the description's hashtags under the headline
    # Height of the source picture band in the STAGE layout (see templates.py presets).
    picture_height: int = STAGE_PICTURE_HEIGHT
    listed: bool = True
    # Hints for the picker preview; the frontend uses them, the renderer does not.
    preview: dict[str, str] | None = None


WHITE = "&H00FFFFFF"
BLACK = "&H00000000"
INK = "&H00222222"  # dark text on light stages
MUTED = "&H00707070"
ACCENT = "&H004FFFD7"  # #D7FF4F (brand lime, legacy karaoke highlight)
YELLOW = "&H003FD2FF"  # #FFD23F gold
RED = "&H002B35E8"  # #E8352B deep red
LIME = "&H0042F5C6"  # #C6F542 yellow-green
SKY = "&H00F5C758"  # #58C7F5 light blue
MAGENTA = "&H00FF4FD7"  # #D74FFF
CYAN = "&H00FFE14F"  # #4FE1FF


def picture_band(style: "CaptionStyle") -> tuple[int, int]:
    """Top and bottom edge of the source picture in the STAGE layout."""
    top = (PLAY_RES_Y - style.picture_height) // 2
    return top, top + style.picture_height


def is_tall_picture(style: "CaptionStyle") -> bool:
    return style.picture_height >= TALL_PICTURE_HEIGHT


def band_caption_margin_v(style: "CaptionStyle") -> int:
    """MarginV for captions on FIT/STAGE: over the picture's lower edge when the
    picture is tall, in the band under it otherwise."""
    _, bottom = picture_band(style)
    if is_tall_picture(style):
        return PLAY_RES_Y - bottom + 110
    return PLAY_RES_Y - (bottom + 216)


def band_headline_y(style: "CaptionStyle") -> int:
    top, _ = picture_band(style)
    return top // 2


def channel_line_y(style: "CaptionStyle") -> int:
    _, bottom = picture_band(style)
    centre = (bottom + PLAY_RES_Y) // 2
    return centre + 50 if is_tall_picture(style) and style.hashtags else centre


def _band_y(value: int, style: "CaptionStyle") -> int:
    """Scale a y designed for the 656 px band to this style's band above the picture."""
    top, _ = picture_band(style)
    return round(value * top / DESIGN_BAND_HEIGHT)


def ass_color(hex_color: str) -> str:
    """#RRGGBB -> &H00BBGGRR."""
    value = hex_color.lstrip("#")
    return f"&H00{value[4:6]}{value[2:4]}{value[0:2]}".upper()


def _is_light(hex_color: str) -> bool:
    value = hex_color.lstrip("#")
    r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) > 160


def _stage_template(
    *,
    name: str,
    description: str,
    tag: str,
    stage_color: str = "#000000",
    caption_size: int = 56,
    caption_primary: str = WHITE,
    highlight: str | None = None,
    emphasize_longest: bool = False,
    show_caption: bool = True,
    positionable: bool = False,
    text_color: str = WHITE,
    headline_size: int = 76,
    headline_align_left: bool = False,
    tagline: str | None = None,
    header_band: str | None = None,
    kicker: str | None = None,
    hashtags: bool = False,
    preview: dict[str, str],
) -> CaptionStyle:
    light = _is_light(stage_color)
    return CaptionStyle(
        name=name,
        description=description,
        tag=tag,
        font_name="NanumSquareRound",
        font_size=caption_size,
        primary=caption_primary,
        outline=WHITE if light else BLACK,
        back="&H80000000",
        bold=-1,
        border_style=1,
        outline_width=2 if light else 4,
        shadow=0,
        margin_v=300,
        highlight=highlight,
        emphasize_longest=emphasize_longest,
        show_caption=show_caption,
        positionable=positionable,
        stage_color=stage_color,
        text_color=text_color,
        headline_size=headline_size,
        headline_align_left=headline_align_left,
        tagline=tagline,
        header_band=header_band,
        kicker=kicker,
        hashtags=hashtags,
        preview={"stage": stage_color, **preview},
    )


def _headline_template(
    *,
    name: str,
    description: str,
    accent: str,
    accent_css: str,
    box: bool = False,
    caption_box: bool = False,
) -> CaptionStyle:
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
        tag="헤드라인",
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
        channel_line=False,
        listed=False,
        preview=preview,
    )


TEMPLATE_STYLES: dict[RenderTemplate, CaptionStyle] = {
    RenderTemplate.CAPTION_POP: _stage_template(
        name="자막 팝형",
        description="핵심 어절을 크고 리듬감 있게. 검은 배경에 제목과 큰 자막.",
        tag="자막",
        caption_size=72,
        emphasize_longest=True,
        positionable=True,
        preview={"caption": "pop", "weight": "900", "positionable": "true"},
    ),
    RenderTemplate.CAPTION_ACCENT: _stage_template(
        name="자막 강조형",
        description="말하는 어절만 브랜드 컬러로. 단어 타이밍을 따라 색이 바뀝니다.",
        tag="자막",
        caption_size=62,
        highlight=BRAND,
        positionable=True,
        preview={"caption": "karaoke", "weight": "800", "positionable": "true"},
    ),
    RenderTemplate.DARK_MINIMAL: _stage_template(
        name="다크 미니멀",
        description="제목과 영상만. 자막 없이 깔끔하게.",
        tag="미니멀",
        show_caption=False,
        preview={"caption": "none", "weight": "800"},
    ),
    RenderTemplate.PAPER: _stage_template(
        name="페이퍼",
        description="종이 느낌의 밝은 배경에 짙은 글씨. 차분한 정보 영상에.",
        tag="밝은 배경",
        stage_color="#F5F1E8",
        caption_primary=INK,
        text_color=INK,
        preview={"caption": "plain", "weight": "800", "color": "#222222"},
    ),
    RenderTemplate.SNS_CARD: _stage_template(
        name="SNS 템플릿",
        description="태그 말풍선, 채널명, 제목, 해시태그를 카드처럼. 흰 배경.",
        tag="카드",
        stage_color="#FFFFFF",
        caption_primary=INK,
        text_color=INK,
        headline_size=62,
        headline_align_left=True,
        tagline="다시 보게 되는 순간",
        hashtags=True,
        preview={"caption": "plain", "weight": "800", "color": "#222222", "tagline": "다시 보게 되는 순간"},
    ),
    RenderTemplate.COMMUNITY: _stage_template(
        name="커뮤니티 템플릿",
        description="‘오늘의 화제’ 헤더와 게시글 느낌의 제목. 흰 배경.",
        tag="카드",
        stage_color="#FFFFFF",
        caption_primary=INK,
        text_color=INK,
        headline_size=60,
        headline_align_left=True,
        header_band="오늘의 화제",
        kicker="실시간 베스트",
        preview={"caption": "plain", "weight": "800", "color": "#222222", "headerBand": "오늘의 화제", "kicker": "실시간 베스트"},
    ),
    RenderTemplate.HEADLINE_YELLOW: _headline_template(
        name="헤드라인 옐로",
        description="큰 제목에 노란 키워드, 아래에 작은 자막.",
        accent=YELLOW,
        accent_css="#FFD23F",
    ),
    RenderTemplate.HEADLINE_RED: _headline_template(
        name="헤드라인 레드",
        description="빨간 키워드로 긴장감을 주는 제목.",
        accent=RED,
        accent_css="#E8352B",
    ),
    RenderTemplate.HEADLINE_LIME: _headline_template(
        name="헤드라인 라임",
        description="연두 키워드.",
        accent=LIME,
        accent_css="#C6F542",
    ),
    RenderTemplate.HEADLINE_SKY: _headline_template(
        name="헤드라인 뉴스",
        description="하늘색 키워드와 박스 자막.",
        accent=SKY,
        accent_css="#58C7F5",
        caption_box=True,
    ),
    RenderTemplate.HEADLINE_BOX: _headline_template(
        name="헤드라인 박스",
        description="제목을 검은 박스 위에.",
        accent=YELLOW,
        accent_css="#FFD23F",
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
        channel_line=False,
        listed=False,
        preview={"color": "#FFFFFF", "stroke": "#000000", "accent": "#FFD23F", "weight": "900"},
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
        channel_line=False,
        listed=False,
        preview={"color": "#FFFFFF", "background": "#111111", "accent": "#D7FF4F", "weight": "900"},
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
        headline_accent=YELLOW,
        channel_line=False,
        listed=False,
        preview={"color": "#FFFFFF", "stroke": "#000000", "weight": "700"},
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
        channel_line=False,
        listed=False,
        preview={"color": "#D7FF4F", "background": "#111111", "weight": "800"},
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
        channel_line=False,
        listed=False,
        preview={"color": "#FFFFFF", "stroke": "#000000", "weight": "400"},
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
        channel_line=False,
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
        channel_line=False,
        listed=False,
        preview={"color": "#4FE1FF", "stroke": "#D74FFF", "weight": "800", "glow": "true"},
    ),
    RenderTemplate.HANDWRITING: CaptionStyle(
        name="Handwriting",
        description="손글씨 느낌의 따뜻한 자막.",
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
        channel_line=False,
        listed=False,
        preview={"color": "#FFFFFF", "stroke": "#303030", "weight": "400", "font": "cursive"},
    ),
    RenderTemplate.TYPEWRITER: CaptionStyle(
        name="Typewriter",
        description="고정폭 글씨와 검은 박스.",
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
        channel_line=False,
        listed=False,
        preview={"color": "#D7FF4F", "background": "#000000", "weight": "700", "font": "monospace"},
    ),
}

BRAND_SWATCHES: list[dict[str, str]] = [
    {"id": "red", "name": "레드", "hex": "#FF4D4F"},
    {"id": "coral", "name": "코랄", "hex": "#FF7A59"},
    {"id": "gold", "name": "골드", "hex": "#FFD23F"},
    {"id": "aqua", "name": "아쿠아", "hex": DEFAULT_BRAND_COLOR},
    {"id": "blue", "name": "블루", "hex": "#3B82F6"},
]


def template_catalog_entry(template_id: str, style: CaptionStyle) -> dict[str, Any]:
    """What the picker needs for one template: id, names, tag, preview hints, flags."""
    return {
        "id": template_id,
        "name": style.name,
        "description": style.description,
        "tag": style.tag,
        "karaoke": style.highlight is not None,
        "preview": {
            **(style.preview or {}),
            "stage": style.stage_color,
            "channel": "true" if style.channel_line else "false",
            "hashtags": "true" if style.hashtags else "false",
            # Picture band as a fraction of the frame height; the preview draws it there.
            "picture": f"{style.picture_height / PLAY_RES_Y:.3f}",
        },
    }


def template_catalog() -> list[dict[str, Any]]:
    return [
        template_catalog_entry(template.value, style)
        for template, style in TEMPLATE_STYLES.items()
        if style.listed
    ]


def layout_catalog() -> list[dict[str, str]]:
    return [
        {
            "id": RenderLayout.STAGE.value,
            "name": "제목 + 원본",
            "description": "템플릿 배경 가운데에 원본 화면을 그대로 두고, 위에는 제목, 아래에는 자막을 넣습니다.",
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


def caption_position_catalog() -> list[dict[str, str]]:
    return [
        {
            "id": CaptionPosition.BOTTOM.value,
            "name": "하단",
            "description": "원본 영상에 자막이 없을 때. 화면을 덜 가리며 내용을 안정적으로 전달해요.",
        },
        {
            "id": CaptionPosition.MIDDLE.value,
            "name": "중앙",
            "description": "짧은 대사·몰입형 장면. 간헐적 자막에 시선을 빠르게 모아줘요.",
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
_HASHTAG = re.compile(r"#[^\s#]+")


def headline_keyword(title: str) -> str | None:
    """The part to colour.

    A ``[bracketed]`` phrase if the user marked one; otherwise the whole second line of
    a two-line title (the usual showcase look), else the longest word of a one-liner.
    """
    marked = _BRACKET.search(title)
    if marked:
        return marked.group(1).strip() or None
    lines = [" ".join(line.split()) for line in title.replace("\r", "").split("\n")]
    lines = [line for line in lines if line]
    if len(lines) >= 2:
        return lines[1]
    return longest_word(title)


def longest_word(text: str) -> str | None:
    words = [w for w in re.split(r"\s+", text.strip()) if len(w) >= 2]
    if len(words) < 2:
        return None
    return max(words, key=len)


def _coloured(text: str, keyword: str | None, accent: str, base: str) -> str:
    """ASS text with ``keyword`` (first occurrence) in ``accent`` and the rest in ``base``."""
    stripped = text.replace("[", "").replace("]", "")
    # Keep the user's line breaks; _ass_text alone would collapse them.
    plain = "\\N".join(_ass_text(line) for line in stripped.split("\n") if line.strip())
    if not keyword:
        return plain
    keyword = _ass_text(keyword)
    return plain.replace(keyword, f"{{\\1c{accent}}}{keyword}{{\\1c{base}}}", 1)


def remap_cues(
    cues: list[CaptionCue], segments: list[tuple[float, float]]
) -> list[CaptionCue]:
    """Re-time cues for a jump-cut render that keeps only ``segments`` (absolute times).

    The result is expressed on the output clock, which starts at 0 at the first kept
    segment. A moment inside a removed gap lands on the start of the next kept
    segment; cues left shorter than a readable flash are dropped.
    """
    ordered = sorted(segments)
    offsets: list[float] = []
    elapsed = 0.0
    for seg_start, seg_end in ordered:
        offsets.append(elapsed)
        elapsed += seg_end - seg_start
    total = elapsed

    def to_output(moment: float) -> float:
        for (seg_start, seg_end), offset in zip(ordered, offsets):
            if moment < seg_start:
                return offset  # inside a removed gap before this segment
            if moment <= seg_end:
                return offset + (moment - seg_start)
        return total

    remapped: list[CaptionCue] = []
    for cue in cues:
        start = to_output(cue.start_seconds)
        end = to_output(cue.end_seconds)
        if end - start < MIN_CUE_SECONDS:
            continue
        words = None
        if cue.words:
            words = []
            for word in cue.words:
                w_start = to_output(word.start_seconds)
                w_end = to_output(word.end_seconds)
                if w_end > w_start:
                    words.append(CaptionWord(start_seconds=w_start, end_seconds=w_end, text=word.text))
            words = words or None
        remapped.append(CaptionCue(start_seconds=start, end_seconds=end, text=cue.text, words=words))
    return remapped


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


@dataclass(frozen=True)
class _Palette:
    """Colours resolved for one render: brand accent plus stage-aware text colours."""

    brand: str
    text: str  # headline / chrome
    caption: str
    caption_outline: str
    caption_outline_width: int
    on_stage: bool  # STAGE layout: chrome and stage colours apply

    def resolve(self, color: str) -> str:
        return self.brand if color == BRAND else color


def _palette(style: CaptionStyle, *, layout: RenderLayout, brand_color: str | None) -> _Palette:
    brand = ass_color(brand_color or DEFAULT_BRAND_COLOR)
    on_stage = layout == RenderLayout.STAGE
    if on_stage:
        caption = brand if style.primary == BRAND else style.primary
        return _Palette(
            brand=brand,
            text=style.text_color,
            caption=caption,
            caption_outline=style.outline,
            caption_outline_width=style.outline_width,
            on_stage=True,
        )
    # Over video (FIT/FILL) light-stage text colours would vanish: keep white on black.
    caption = brand if style.primary == BRAND else (WHITE if style.primary == INK else style.primary)
    return _Palette(
        brand=brand,
        text=WHITE,
        caption=caption,
        caption_outline=BLACK if style.outline == WHITE else style.outline,
        # Light-stage templates have a thin light outline; over video they need a real one.
        caption_outline_width=max(style.outline_width, 3) if style.outline == WHITE else style.outline_width,
        on_stage=False,
    )


def _style_line(
    name: str,
    style: CaptionStyle,
    *,
    alignment: int,
    margin_v: int,
    primary: str,
    outline: str,
    outline_width: int,
) -> str:
    return (
        f"Style: {name},{style.font_name},{style.font_size},{primary},&H000000FF,"
        f"{outline},{style.back},{style.bold},{style.italic},0,0,100,100,{style.spacing},0,"
        f"{style.border_style},{outline_width},{style.shadow},{alignment},90,90,{margin_v},1"
    )


def _headline_style_line(style: CaptionStyle, palette: _Palette) -> str:
    if style.headline_box:
        border_style, outline, back = 3, 18, "&H90000000"
        outline_color = BLACK
    elif palette.on_stage and _is_light(style.stage_color):
        border_style, outline, back = 1, 0, "&H00000000"
        outline_color = WHITE
    else:
        border_style, outline, back = 1, 5, "&H80000000"
        outline_color = BLACK
    alignment = 7 if (style.headline_align_left and palette.on_stage) else 5
    return (
        f"Style: Headline,{style.headline_font},{style.headline_size},{palette.text},&H000000FF,"
        f"{outline_color},{back},-1,0,0,0,100,100,0,0,{border_style},{outline},0,{alignment},"
        f"{HEADLINE_MARGIN_X},{HEADLINE_MARGIN_X},0,1"
    )


def _chrome_style_line(palette: _Palette) -> str:
    outline_color = BLACK if palette.text == WHITE else WHITE
    return (
        f"Style: Chrome,NanumSquareRound,36,{palette.text},&H000000FF,{outline_color},"
        f"&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,{HEADLINE_MARGIN_X},{HEADLINE_MARGIN_X},0,1"
    )


def _header(
    style: CaptionStyle,
    *,
    layout: RenderLayout,
    palette: _Palette,
    caption_position: CaptionPosition,
    band_margin_v: int | None = None,
) -> tuple[list[str], str, int]:
    """ASS header, the global override prefix (blur) for every event, and the MarginV used."""
    if caption_position == CaptionPosition.MIDDLE:
        alignment, margin_v = 5, 0
    elif layout in (RenderLayout.FIT, RenderLayout.STAGE):
        alignment = 2
        margin_v = band_margin_v if band_margin_v is not None else band_caption_margin_v(style)
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
        _style_line(
            "Default",
            style,
            alignment=alignment,
            margin_v=margin_v,
            primary=palette.caption,
            outline=palette.caption_outline,
            outline_width=palette.caption_outline_width,
        ),
        _headline_style_line(style, palette),
        _chrome_style_line(palette),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    prefix = f"{{\\blur{style.blur:g}}}" if style.blur else ""
    return lines, prefix, margin_v


def _rect(x: int, y: int, width: int, height: int, color: str, *, start: str, end: str, alpha: str = "00") -> str:
    return (
        f"Dialogue: 0,{start},{end},Chrome,,0,0,0,,"
        f"{{\\an7\\pos({x},{y})\\1c{color}&\\1a&H{alpha}&\\bord0\\shad0\\p1}}"
        f"m 0 0 l {width} 0 l {width} {height} l 0 {height}{{\\p0}}"
    )


def _chrome_events(
    style: CaptionStyle,
    palette: _Palette,
    *,
    layout: RenderLayout,
    title: str | None,
    channel_name: str | None,
    description: str | None,
    end: str,
    title_intro: bool = False,
) -> list[str]:
    """Headline, pill, band, kicker, hashtags, and channel line for the whole clip."""
    start = _ass_time(0)
    events: list[str] = []
    headline_start = start
    if title and title_intro:
        # Big centred title over a dimmed frame, shrinking away before the headline appears.
        intro_end = _ass_time(INTRO_SECONDS)
        fade_ms = 350
        events.append(
            _rect(0, 0, PLAY_RES_X, PLAY_RES_Y, BLACK, start=start, end=intro_end, alpha="80")
        )
        intro_text = _coloured(title, headline_keyword(title), palette.resolve(style.headline_accent), palette.text)
        events.append(
            f"Dialogue: 3,{start},{intro_end},Headline,,0,0,0,,"
            f"{{\\an5\\pos({PLAY_RES_X // 2},{PLAY_RES_Y // 2})\\fscx{INTRO_SCALE}\\fscy{INTRO_SCALE}"
            f"\\fad(200,{fade_ms})\\t({int(INTRO_SECONDS * 1000) - fade_ms},{int(INTRO_SECONDS * 1000)},\\fscx100\\fscy100)}}"
            f"{intro_text}"
        )
        headline_start = intro_end
    accent = palette.resolve(style.headline_accent)
    dark_on_brand = INK
    left_x = HEADLINE_MARGIN_X + 20
    headline_y = FILL_HEADLINE_Y if layout == RenderLayout.FILL else band_headline_y(style)
    tall = is_tall_picture(style)
    _, picture_bottom = picture_band(style)
    bottom_band_centre = (picture_bottom + PLAY_RES_Y) // 2

    if palette.on_stage and style.header_band:
        band_h = _band_y(200, style)
        events.append(_rect(0, 0, PLAY_RES_X, band_h, palette.brand, start=start, end=end))
        events.append(
            f"Dialogue: 2,{start},{end},Headline,,0,0,0,,{{\\an5\\pos({PLAY_RES_X // 2},{band_h // 2})"
            f"\\1c{dark_on_brand}\\bord0}}{_ass_text(style.header_band)}"
        )
    if palette.on_stage and style.kicker:
        events.append(
            f"Dialogue: 2,{start},{end},Chrome,,0,0,0,,{{\\an7\\pos({left_x},{_band_y(250, style)})\\1c{palette.brand}}}"
            f"{_ass_text(style.kicker)}"
        )
    if palette.on_stage and style.tagline:
        pill_w, pill_h = 620, 84
        pill_y = _band_y(200, style)
        events.append(
            _rect((PLAY_RES_X - pill_w) // 2, pill_y, pill_w, pill_h, palette.brand, start=start, end=end)
        )
        events.append(
            f"Dialogue: 2,{start},{end},Chrome,,0,0,0,,{{\\an5\\pos({PLAY_RES_X // 2},{pill_y + pill_h // 2})"
            f"\\fs40\\1c{dark_on_brand}}}{_ass_text(style.tagline)}"
        )

    if title:
        keyword = headline_keyword(title)
        text = _coloured(title, keyword, accent, palette.text)
        fade = "\\fad(200,0)" if headline_start != start else ""
        if palette.on_stage and style.headline_align_left:
            # Leave space for two title lines and hashtags above the picture.
            y = _band_y(300 if style.kicker else (340 if style.tagline else 280), style)
            events.append(
                f"Dialogue: 2,{headline_start},{end},Headline,,0,0,0,,{{\\an7\\pos({left_x},{y}){fade}}}{text}"
            )
        elif palette.on_stage and style.tagline:
            events.append(
                f"Dialogue: 2,{headline_start},{end},Headline,,0,0,0,,{{\\an5\\pos({PLAY_RES_X // 2},{_band_y(440, style)}){fade}}}{text}"
            )
        else:
            events.append(
                f"Dialogue: 2,{headline_start},{end},Headline,,0,0,0,,{{\\an5\\pos({PLAY_RES_X // 2},{headline_y}){fade}}}{text}"
            )

    if palette.on_stage and style.hashtags and description:
        tags = " ".join(_HASHTAG.findall(description))
        tags = tags if len(tags) <= 24 else tags[:24] + "…"
        if tags and tall:
            # Tall picture: the hashtags live in the band under the picture.
            tag_y = bottom_band_centre - (40 if style.channel_line and channel_name else 0)
            events.append(
                f"Dialogue: 2,{start},{end},Chrome,,0,0,0,,{{\\an5\\pos({PLAY_RES_X // 2},{tag_y})\\q2\\fs44\\1c{palette.text}}}"
                f"{_ass_text(tags)}"
            )
        elif tags:
            events.append(
                f"Dialogue: 2,{start},{end},Chrome,,0,0,0,,{{\\an7\\pos({left_x},{_band_y(520, style)})\\q2\\1c{palette.brand}}}"
                f"{_ass_text(tags)}"
            )

    if channel_name and style.channel_line and layout != RenderLayout.FILL:
        channel = channel_name if len(channel_name) <= 20 else channel_name[:20] + "…"
        label = f"{{\\fs30}}●{{\\fs44}}  {_ass_text(channel)}"
        events.append(
            f"Dialogue: 2,{start},{end},Chrome,,0,0,0,,{{\\an5\\pos({PLAY_RES_X // 2},{channel_line_y(style)})\\q2}}{label}"
        )
    return events


def _bar_event(style: CaptionStyle, *, start: float, end: float, margin_v: int) -> str:
    """Full-width translucent band behind a bottom-aligned cue (news lower third)."""
    centre = PLAY_RES_Y - margin_v - style.font_size // 2
    top = centre - style.bar_height // 2
    return _rect(
        0, top, PLAY_RES_X, style.bar_height, f"&H{style.back[4:]}", start=_ass_time(start), end=_ass_time(end), alpha="30"
    ).replace("\\1c&H&H", "\\1c&H")


def _karaoke_events(
    cue: CaptionCue, *, highlight: str, base: str, offset: float, prefix: str
) -> list[str]:
    """One event per word: the whole line stays visible, the current word is coloured."""
    assert cue.words
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
                parts.append(f"{{\\1c{highlight}}}{text}{{\\1c{base}}}")
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
    layout: RenderLayout = RenderLayout.STAGE,
    title: str | None = None,
    brand_color: str | None = None,
    caption_position: CaptionPosition = CaptionPosition.BOTTOM,
    channel_name: str | None = None,
    description: str | None = None,
    title_intro: bool = False,
    style: CaptionStyle | None = None,
) -> str:
    """Return an ASS document whose times are relative to the clip start.

    ``style`` overrides the template's preset (a creator's own template); ``template``
    is still recorded on the job for the catalog and defaults.
    """
    style = style or TEMPLATE_STYLES[template]
    palette = _palette(style, layout=layout, brand_color=brand_color)
    if not style.positionable:
        # Card and paper layouts keep the caption in the band under the picture.
        caption_position = CaptionPosition.BOTTOM
    lines, prefix, margin_v = _header(
        style, layout=layout, palette=palette, caption_position=caption_position
    )
    clip_end = _ass_time(clip_end_seconds - clip_start_seconds)
    lines.extend(
        _chrome_events(
            style,
            palette,
            layout=layout,
            title=title.strip()[:MAX_TITLE_CHARS] if title and title.strip() else None,
            channel_name=channel_name.strip() if channel_name and channel_name.strip() else None,
            description=description,
            end=clip_end,
            title_intro=title_intro,
        )
    )
    if not style.show_caption:
        return "\n".join(lines) + "\n"
    highlight = palette.resolve(style.highlight) if style.highlight else None
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
        if highlight and cue.words and len(cue.words) > 1:
            lines.extend(
                _karaoke_events(
                    cue, highlight=highlight, base=palette.caption, offset=clip_start_seconds, prefix=prefix
                )
            )
            continue
        if style.emphasize_longest or highlight:
            text = _coloured(cue.text, longest_word(cue.text), highlight or palette.brand, palette.caption)
        else:
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
    headline: str | None = None,
    brand_color: str | None = None,
    caption_position: CaptionPosition = CaptionPosition.BOTTOM,
) -> str:
    """ASS for a product Short on the template's stage.

    Geometry (1080x1920): headline band 0..330, picture 330..1230, price badge
    under the picture, spoken captions in the band below, CTA and the affiliate
    disclosure pinned at the bottom for the whole clip.
    """
    style = TEMPLATE_STYLES[template]
    palette = _palette(style, layout=RenderLayout.STAGE, brand_color=brand_color)
    if not style.positionable:
        caption_position = CaptionPosition.BOTTOM
    # Product Shorts keep their own 900 px picture box; captions sit in the band under it.
    lines, prefix, _ = _header(
        style,
        layout=RenderLayout.STAGE,
        palette=palette,
        caption_position=caption_position,
        band_margin_v=440,
    )
    light = _is_light(style.stage_color)
    badge_back = "&H40FFFFFF" if light else "&H40000000"
    badge_text = INK if light else WHITE
    # Price badge, CTA, and disclosure styles live next to Default/Headline/Chrome.
    styles_end = lines.index("[Events]") - 1  # the blank line that closes [V4+ Styles]
    lines[styles_end:styles_end] = [
        f"Style: Price,NanumSquareRound,52,{palette.brand},&H000000FF,{badge_back},{badge_back},-1,0,0,0,"
        "100,100,0,0,3,16,0,8,80,80,0,1",
        f"Style: Cta,NanumSquareRound,44,{badge_text},&H000000FF,{badge_back},{badge_back},-1,0,0,0,"
        "100,100,0,0,3,12,0,2,80,80,250,1",
        f"Style: Disclosure,NanumSquareRound,28,{MUTED},&H000000FF,&H00000000,&H00000000,0,0,0,0,"
        "100,100,0,0,1,0,0,2,60,60,60,1",
    ]
    start, end = _ass_time(0), _ass_time(total_seconds)
    headline_text = (headline or "").strip() or title
    accent = palette.resolve(style.headline_accent)
    lines.append(
        f"Dialogue: 2,{start},{end},Headline,,0,0,0,,{{\\an5\\pos({PLAY_RES_X // 2},{PRODUCT_HEADLINE_Y})}}"
        f"{_coloured(headline_text[:MAX_TITLE_CHARS], headline_keyword(headline_text), accent, palette.text)}"
    )
    if price_line:
        lines.append(
            f"Dialogue: 2,{start},{end},Price,,0,0,0,,{{\\an8\\pos({PLAY_RES_X // 2},{PRODUCT_PICTURE_BOTTOM + 36})}}"
            f"{_ass_text(price_line)}"
        )
    lines.append(f"Dialogue: 2,{start},{end},Cta,,0,0,0,,{_ass_text(cta)}")
    lines.append(f"Dialogue: 2,{start},{end},Disclosure,,0,0,0,,{_ass_text(disclosure)}")
    if not style.show_caption:
        return "\n".join(lines) + "\n"
    highlight = palette.resolve(style.highlight) if style.highlight else None
    for cue in select_cues(cues, start_seconds=0, end_seconds=total_seconds):
        if style.emphasize_longest or highlight:
            text = _coloured(cue.text, longest_word(cue.text), highlight or palette.brand, palette.caption)
        else:
            text = _ass_text(cue.text)
        if text:
            lines.append(
                f"Dialogue: 1,{_ass_time(cue.start_seconds)},{_ass_time(cue.end_seconds)},"
                f"Default,,0,0,0,,{prefix}{text}"
            )
    return "\n".join(lines) + "\n"
