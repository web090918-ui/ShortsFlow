from app.captions import CaptionCue, build_ass, select_cues
from app.downloads import RenderTemplate


def _cues() -> list[CaptionCue]:
    return [
        CaptionCue(start_seconds=95.0, end_seconds=101.0, text="앞부분 자막"),
        CaptionCue(start_seconds=101.0, end_seconds=104.5, text="안녕하세요 {태그} 여러분\n둘째 줄"),
        CaptionCue(start_seconds=104.5, end_seconds=104.6, text="너무 짧음"),
        CaptionCue(start_seconds=118.0, end_seconds=125.0, text="끝부분 자막"),
        CaptionCue(start_seconds=130.0, end_seconds=133.0, text="범위 밖"),
    ]


def test_select_cues_clamps_to_clip_and_drops_unreadable_fragments() -> None:
    selected = select_cues(_cues(), start_seconds=100, end_seconds=120)

    assert [(c.start_seconds, c.end_seconds, c.text) for c in selected] == [
        (100.0, 101.0, "앞부분 자막"),
        (101.0, 104.5, "안녕하세요 {태그} 여러분\n둘째 줄"),
        (118.0, 120.0, "끝부분 자막"),
    ]


def test_select_cues_trims_overlaps_so_one_cue_shows_at_a_time() -> None:
    cues = [
        CaptionCue(start_seconds=0.0, end_seconds=4.0, text="첫 문장"),
        CaptionCue(start_seconds=2.5, end_seconds=6.0, text="둘째 문장"),
        CaptionCue(start_seconds=5.9, end_seconds=6.1, text="너무 짧아짐"),
        CaptionCue(start_seconds=8.0, end_seconds=10.0, text="셋째 문장"),
    ]

    selected = select_cues(cues, start_seconds=0, end_seconds=20)

    assert [(c.start_seconds, c.end_seconds, c.text) for c in selected] == [
        (0.0, 2.5, "첫 문장"),
        (2.5, 5.9, "둘째 문장"),
        (8.0, 10.0, "셋째 문장"),
    ]
    for first, second in zip(selected, selected[1:]):
        assert first.end_seconds <= second.start_seconds


def test_build_ass_uses_clip_relative_times_and_template_style() -> None:
    document = build_ass(
        _cues(),
        template=RenderTemplate.BOLD_HIGHLIGHT,
        clip_start_seconds=100,
        clip_end_seconds=120,
    )

    assert "PlayResX: 1080" in document and "PlayResY: 1920" in document
    assert "Style: Default,NanumGothic,80,&H004FFFD7," in document
    # BorderStyle 3 draws the opaque box that makes the highlight template.
    assert ",-1,0,0,0,100,100,0,0,3,16,0,2,90,90,520,1" in document
    dialogues = [line for line in document.splitlines() if line.startswith("Dialogue:")]
    assert dialogues == [
        "Dialogue: 1,0:00:00.00,0:00:01.00,Default,,0,0,0,,앞부분 자막",
        "Dialogue: 1,0:00:01.00,0:00:04.50,Default,,0,0,0,,안녕하세요 태그 여러분 둘째 줄",
        "Dialogue: 1,0:00:18.00,0:00:20.00,Default,,0,0,0,,끝부분 자막",
    ]


def test_every_template_renders_a_distinct_document() -> None:
    documents = {
        template: build_ass(
            _cues(),
            template=template,
            clip_start_seconds=100,
            clip_end_seconds=120,
            title="이 장면 하나로 [채널]이 달라집니다",
        )
        for template in RenderTemplate
    }
    styles = {
        template: next(line for line in doc.splitlines() if line.startswith("Style: Default"))
        for template, doc in documents.items()
    }

    assert len(set(documents.values())) == len(RenderTemplate)
    assert ",64,&H00FFFFFF," in styles[RenderTemplate.CLEAN_CAPTION]
    assert ",48,&H00FFFFFF," in styles[RenderTemplate.MINIMAL]
    assert styles[RenderTemplate.MINIMAL].endswith(",1,2,0,2,90,90,180,1")


def test_build_ass_with_long_clip_formats_hours() -> None:
    cues = [CaptionCue(start_seconds=3700, end_seconds=3705, text="한 시간 뒤")]

    document = build_ass(
        cues, template=RenderTemplate.CLEAN_CAPTION, clip_start_seconds=0, clip_end_seconds=3800
    )

    assert "Dialogue: 1,1:01:40.00,1:01:45.00,Default,,0,0,0,,한 시간 뒤" in document


def test_fit_layout_moves_captions_below_the_source_picture() -> None:
    from app.templates import RenderLayout

    document = build_ass(
        _cues(),
        template=RenderTemplate.IMPACT_YELLOW,
        clip_start_seconds=100,
        clip_end_seconds=120,
        layout=RenderLayout.FIT,
    )
    style = next(line for line in document.splitlines() if line.startswith("Style:"))

    # Bottom-centre (2) with MarginV 440 sits in the blurred band under a 1080x607 picture
    # instead of the template's own middle-of-frame alignment.
    assert style.endswith(",2,90,90,440,1")
    assert "Style: Default,NanumSquareRound,74," in style


def test_karaoke_template_emits_one_event_per_word_with_the_spoken_word_coloured() -> None:
    from app.captions import CaptionWord

    cue = CaptionCue(
        start_seconds=10.0,
        end_seconds=13.0,
        text="오늘 핵심 장면",
        words=[
            CaptionWord(start_seconds=10.0, end_seconds=11.0, text="오늘"),
            CaptionWord(start_seconds=11.0, end_seconds=12.0, text="핵심"),
            CaptionWord(start_seconds=12.0, end_seconds=13.0, text="장면"),
        ],
    )

    document = build_ass(
        [cue], template=RenderTemplate.IMPACT_YELLOW, clip_start_seconds=10, clip_end_seconds=20
    )
    dialogues = [line for line in document.splitlines() if line.startswith("Dialogue:")]

    assert dialogues == [
        "Dialogue: 1,0:00:00.00,0:00:01.00,Default,,0,0,0,,{\\1c&H003FD2FF}오늘{\\r} 핵심 장면",
        "Dialogue: 1,0:00:01.00,0:00:02.00,Default,,0,0,0,,오늘 {\\1c&H003FD2FF}핵심{\\r} 장면",
        "Dialogue: 1,0:00:02.00,0:00:03.00,Default,,0,0,0,,오늘 핵심 {\\1c&H003FD2FF}장면{\\r}",
    ]


def test_karaoke_template_without_word_timings_falls_back_to_whole_cue() -> None:
    document = build_ass(
        _cues(), template=RenderTemplate.KARAOKE_POP, clip_start_seconds=100, clip_end_seconds=120
    )
    dialogues = [line for line in document.splitlines() if line.startswith("Dialogue:")]

    assert len(dialogues) == 3
    assert dialogues[0].endswith(",,앞부분 자막")


def test_neon_template_applies_blur_to_every_event() -> None:
    document = build_ass(
        _cues(), template=RenderTemplate.NEON_GLOW, clip_start_seconds=100, clip_end_seconds=120
    )

    for line in document.splitlines():
        if line.startswith("Dialogue:"):
            assert ",,{\\blur6}" in line


def test_select_cues_clamps_word_timings_to_the_clip() -> None:
    from app.captions import CaptionWord

    cue = CaptionCue(
        start_seconds=98.0,
        end_seconds=103.0,
        text="하나 둘 셋",
        words=[
            CaptionWord(start_seconds=98.0, end_seconds=99.5, text="하나"),
            CaptionWord(start_seconds=99.5, end_seconds=101.0, text="둘"),
            CaptionWord(start_seconds=101.0, end_seconds=103.0, text="셋"),
        ],
    )

    [selected] = select_cues([cue], start_seconds=100, end_seconds=120)

    assert selected.words is not None
    assert [(w.text, w.start_seconds, w.end_seconds) for w in selected.words] == [
        ("둘", 100.0, 101.0),
        ("셋", 101.0, 103.0),
    ]



def test_news_bar_draws_a_full_width_band_under_each_cue() -> None:
    document = build_ass(
        _cues(), template=RenderTemplate.NEWS_BAR, clip_start_seconds=100, clip_end_seconds=120
    )
    dialogues = [line for line in document.splitlines() if line.startswith("Dialogue:")]

    bars = [line for line in dialogues if r"\p1}" in line]
    texts = [line for line in dialogues if r"\p1}" not in line]
    assert len(bars) == len(texts) == 3
    # Band: layer 0, full PlayResX width, centred on the text (MarginV 240, font 58).
    assert bars[0].startswith(
        r"Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,{\an7\pos(0,1586)\1c&H202020&"
    )
    assert "m 0 0 l 1080 0 l 1080 130 l 0 130" in bars[0]
    assert texts[0].startswith("Dialogue: 1,0:00:00.00,0:00:01.00,")


def test_headline_is_drawn_for_the_whole_clip_with_the_keyword_coloured() -> None:
    from app.templates import RenderLayout

    document = build_ass(
        _cues(),
        template=RenderTemplate.HEADLINE_RED,
        clip_start_seconds=100,
        clip_end_seconds=120,
        layout=RenderLayout.STAGE,
        title="독립을 위해 [목숨]을 건 여자",
    )
    lines = document.splitlines()
    headline = next(line for line in lines if ",Headline,," in line)

    assert "Style: Headline,NanumSquareRound,84,&H00FFFFFF," in document
    # Layer 2, full clip, centred in the band above the picture (y = 328).
    assert headline.startswith("Dialogue: 2,0:00:00.00,0:00:20.00,Headline,,0,0,0,,{\\an5\\pos(540,328)}")
    assert headline.endswith("독립을 위해 {\\1c&H002B35E8}목숨{\\1c&H00FFFFFF}을 건 여자")
    # Captions still sit in the band under the picture.
    assert ",2,90,90,440,1" in next(line for line in lines if line.startswith("Style: Default"))


def test_headline_colours_the_second_line_or_the_longest_word_when_nothing_is_marked() -> None:
    from app.captions import headline_keyword
    from app.templates import RenderLayout

    assert headline_keyword("엘니뇨 현상으로 유럽과 한국 여름이 바뀌었다?") == "바뀌었다?"
    assert headline_keyword("한단어") is None
    assert headline_keyword("암표 수수료도\n이제 다 [제 겁니다]") == "제 겁니다"
    # Two lines without brackets: the whole second line, like the showcase thumbnails.
    assert headline_keyword("엘니뇨 현상으로\n유럽과 한국 여름이 바뀌었다?") == "유럽과 한국 여름이 바뀌었다?"

    document = build_ass(
        [],
        template=RenderTemplate.HEADLINE_YELLOW,
        clip_start_seconds=0,
        clip_end_seconds=30,
        layout=RenderLayout.FILL,
        title="엘니뇨 현상으로\n여름이 바뀌었다",
    )
    headline = next(line for line in document.splitlines() if ",Headline,," in line)
    # FILL overlays the headline near the top; user line breaks become \\N.
    assert "{\\an5\\pos(540,230)}엘니뇨 현상으로\\N{\\1c&H003FD2FF}여름이 바뀌었다{\\1c&H00FFFFFF}" in headline


def test_headline_box_template_uses_an_opaque_box_style() -> None:
    document = build_ass(
        _cues(), template=RenderTemplate.HEADLINE_BOX, clip_start_seconds=100, clip_end_seconds=120
    )
    headline_style = next(line for line in document.splitlines() if line.startswith("Style: Headline"))

    assert ",-1,0,0,0,100,100,0,0,3,18,0,5,70,70,0,1" in headline_style
    assert ",Headline,," not in document  # no title, no headline event
