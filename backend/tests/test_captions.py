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
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,앞부분 자막",
        "Dialogue: 0,0:00:01.00,0:00:04.50,Default,,0,0,0,,안녕하세요 태그 여러분 둘째 줄",
        "Dialogue: 0,0:00:18.00,0:00:20.00,Default,,0,0,0,,끝부분 자막",
    ]


def test_templates_differ_only_in_style_values() -> None:
    styles = {
        template: next(
            line
            for line in build_ass(
                _cues(), template=template, clip_start_seconds=100, clip_end_seconds=120
            ).splitlines()
            if line.startswith("Style:")
        )
        for template in RenderTemplate
    }

    assert len(set(styles.values())) == 3
    assert ",64,&H00FFFFFF," in styles[RenderTemplate.CLEAN_CAPTION]
    assert ",48,&H00FFFFFF," in styles[RenderTemplate.MINIMAL]
    assert styles[RenderTemplate.MINIMAL].endswith(",1,2,0,2,90,90,180,1")


def test_build_ass_with_long_clip_formats_hours() -> None:
    cues = [CaptionCue(start_seconds=3700, end_seconds=3705, text="한 시간 뒤")]

    document = build_ass(
        cues, template=RenderTemplate.CLEAN_CAPTION, clip_start_seconds=0, clip_end_seconds=3800
    )

    assert "Dialogue: 0,1:01:40.00,1:01:45.00,Default,,0,0,0,,한 시간 뒤" in document
