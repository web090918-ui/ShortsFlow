from pathlib import Path

import pytest

from app import product_pipeline as pipeline_module
from app.downloads import RenderTemplate
from app.product_content import ContentAngle
from app.product_pipeline import ProductShortPipeline, price_line
from app.products import ProductFacts
from app.shorts_pipeline import ShortErrorCode, ShortPipelineError, StoredArtifact
from app.tts import SpeechSynthesisError
from app.video_processing import VideoInfo


def _facts() -> ProductFacts:
    return ProductFacts(
        provider="coupang_partners",
        product_id="7310929139",
        title="코카콜라 오리지널 무라벨, 370ml, 24개",
        origin_price=28600,
        sales_price=17990,
        discount_rate=37,
        image_url="https://thumbnail5.coupangcdn.com/thumbnails/remote/1000x1000ex/a.jpg",
        product_url="https://www.coupang.com/vp/products/7310929139",
        facts=["판매가 17,990원"],
    )


def _angle(sentences: int = 3) -> ContentAngle:
    return ContentAngle(
        id="angle_deal",
        name="가격 앵글",
        summary="요약",
        hook="코카콜라 24캔이 만 칠천 원대?",
        script=[f"문장 {i}" for i in range(1, sentences + 1)],
        cta="링크에서 확인하세요.",
    )


class StubSynth:
    name = "stub"

    def __init__(self, *, seconds: float = 2.0, fail: bool = False) -> None:
        self.seconds = seconds
        self.fail = fail
        self.texts: list[str] = []

    def synthesize(self, text: str, destination: Path) -> None:
        if self.fail:
            raise SpeechSynthesisError("no tts", retryable=False)
        self.texts.append(text)
        destination.write_bytes(b"mp3")


class StubComposer:
    def __init__(self, synth: StubSynth) -> None:
        self.synth = synth
        self.concat_parts: list[str] = []
        self.compose_kwargs: dict = {}
        self.ass = ""

    def probe(self, media_path: Path) -> VideoInfo:
        if media_path.suffix == ".mp3":
            return VideoInfo(duration_seconds=self.synth.seconds, width=None, height=None)
        return VideoInfo(duration_seconds=12.0, width=1080, height=1920)

    def make_silence(self, destination: Path, *, seconds: float) -> None:
        destination.write_bytes(b"silence")

    def concat_audio(self, parts, output_path: Path) -> None:
        self.concat_parts = [p.name for p in parts]
        output_path.write_bytes(b"aac")

    def compose_product_short(
        self, image_paths, audio_path, output_path, *, duration_seconds, subtitles_path=None, stage_color="#000000"
    ):
        self.compose_kwargs = {
            "duration": duration_seconds,
            "images": [path.read_bytes() for path in image_paths],
            "stage_color": stage_color,
        }
        self.ass = subtitles_path.read_text(encoding="utf-8") if subtitles_path else ""
        output_path.write_bytes(b"video")


class StubStorage:
    def __init__(self) -> None:
        self.keys: list[str] = []
        self.fetched: list[str] = []

    def fetch_to(self, key: str, destination: Path) -> None:
        self.fetched.append(key)
        destination.write_bytes(b"uploaded-image")

    def store(self, file_path, *, key, filename):
        self.keys.append(key)
        return StoredArtifact(storage="stub", key=key, download_url="https://x/y.mp4", local_path=None, expires_at=None, preview_url="https://x/p.mp4")

    def exists(self, key: str) -> bool:
        return True


@pytest.fixture
def fake_image(monkeypatch):
    def fake_download(url, destination, **kwargs):
        destination.write_bytes(b"jpeg")
        return 4

    monkeypatch.setattr(pipeline_module, "download_to_file", fake_download)


def test_price_line_formats_discount_and_origin() -> None:
    assert price_line(_facts()) == "37% 할인 · 17,990원 (정가 28,600원)"
    assert price_line(_facts().model_copy(update={"sales_price": None})) is None


def test_pipeline_narrates_each_line_and_composes_with_template_text(fake_image) -> None:
    synth = StubSynth(seconds=2.0)
    composer = StubComposer(synth)
    storage = StubStorage()
    pipeline = ProductShortPipeline(synth, composer, storage)
    stages = []

    artifact = pipeline.run(
        job_id="job-p",
        facts=_facts(),
        angle=_angle(3),
        template=RenderTemplate.BOLD_HIGHLIGHT,
        report=lambda stage, progress: stages.append(stage.value),
        cta_url="https://link.coupang.com/a/abc",
    )

    # hook + 3 script lines + cta = 5 spoken lines, silence between them.
    assert synth.texts == ["코카콜라 24캔이 만 칠천 원대?", "문장 1", "문장 2", "문장 3", "링크에서 확인하세요."]
    assert composer.concat_parts.count("gap.mp3") == 4
    # 5 lines x 2.0s + 4 gaps x 0.35s + 1.2s tail
    assert composer.compose_kwargs["duration"] == pytest.approx(12.6)
    assert composer.compose_kwargs["images"] == [b"jpeg"]
    assert composer.compose_kwargs["stage_color"] == "#000000"
    assert "Style: Default,NanumGothic,80,&H004FFFD7" in composer.ass
    headline = next(line for line in composer.ass.splitlines() if ",Headline,," in line)
    assert "코카콜라 오리지널" in headline and "24개" in headline
    assert "Style: Price,NanumSquareRound,52," in composer.ass
    assert "37% 할인 · 17,990원 (정가 28,600원)" in composer.ass
    assert "링크에서 확인하세요. · 링크는 설명란에" in composer.ass
    assert "쿠팡 파트너스 활동의 일환" in composer.ass
    assert "Dialogue: 1,0:00:00.00,0:00:02.00,Default,,0,0,0,,코카콜라 24캔이 만 칠천 원대?" in composer.ass
    assert "Dialogue: 1,0:00:02.35,0:00:04.35,Default,,0,0,0,,문장 1" in composer.ass
    assert artifact.provider == "coupang_partners"
    assert artifact.captions_applied == 5
    assert artifact.template_id == "BOLD_HIGHLIGHT"
    assert storage.keys == ["shorts/job-p.mp4"]
    assert stages[0] == "DOWNLOADING" and "UPLOADING" in stages


def test_pipeline_rejects_scripts_longer_than_the_limit(fake_image) -> None:
    synth = StubSynth(seconds=9.0)
    pipeline = ProductShortPipeline(synth, StubComposer(synth), StubStorage(), max_seconds=30)

    with pytest.raises(ShortPipelineError) as excinfo:
        pipeline.run(
            job_id="job-long", facts=_facts(), angle=_angle(4),
            template=RenderTemplate.MINIMAL, report=lambda s, p: None,
        )

    assert excinfo.value.code == ShortErrorCode.INVALID_TIME_RANGE
    assert excinfo.value.retryable is False


def test_pipeline_maps_tts_failures(fake_image) -> None:
    synth = StubSynth(fail=True)
    pipeline = ProductShortPipeline(synth, StubComposer(synth), StubStorage())

    with pytest.raises(ShortPipelineError) as excinfo:
        pipeline.run(
            job_id="job-tts", facts=_facts(), angle=_angle(),
            template=RenderTemplate.CLEAN_CAPTION, report=lambda s, p: None,
        )

    assert excinfo.value.code == ShortErrorCode.TTS_FAILED
    assert excinfo.value.retryable is False


def test_pipeline_slides_through_uploaded_and_remote_pictures_on_the_template_stage(fake_image) -> None:
    from app.templates import CaptionPosition

    synth = StubSynth()
    composer = StubComposer(synth)
    storage = StubStorage()
    pipeline = ProductShortPipeline(synth, composer, storage, max_seconds=60)
    facts = _facts().model_copy(
        update={
            "provider": "manual",
            "image_url": "upload://uploads/img-1.jpg",
            "image_urls": ["upload://uploads/img-1.jpg", "https://images.example.com/second.png"],
        }
    )

    artifact = pipeline.run(
        job_id="job-manual",
        facts=facts,
        angle=_angle(),
        template=RenderTemplate.PAPER,
        report=lambda stage, progress: None,
        headline="30캔 콜라\n[13,200원]에 쟁이기",
        brand_color="#FF4D4F",
        caption_position=CaptionPosition.MIDDLE,
    )

    # Uploaded picture comes from our storage, the second over HTTPS; both reach FFmpeg.
    assert storage.fetched == ["uploads/img-1.jpg"]
    assert composer.compose_kwargs["images"] == [b"uploaded-image", b"jpeg"]
    assert composer.compose_kwargs["stage_color"] == "#F5F1E8"
    # Headline keyword in brand red (#FF4D4F -> &H004F4DFF) on dark paper text.
    assert "{\\1c&H004F4DFF}13,200원{\\1c&H00222222}" in composer.ass
    assert "Style: Price,NanumSquareRound,52,&H004F4DFF," in composer.ass
    # PAPER keeps captions in the band (not positionable) even when MIDDLE was asked.
    assert next(line for line in composer.ass.splitlines() if line.startswith("Style: Default")).endswith(
        ",2,90,90,440,1"
    )
    assert artifact.title == "30캔 콜라\n[13,200원]에 쟁이기"
    assert artifact.brand_color == "#FF4D4F"
