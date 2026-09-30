"""Task 10: product facts + content angle -> narrated, captioned 9:16 Short.

Steps: fetch the product image, synthesize each spoken line, measure the clips,
join them, write the template ASS (title, price, speech cues, CTA, disclosure),
compose the video with FFmpeg, and store it through the same ArtifactStorage as
the YouTube Shorts so preview, download, and artifact states are shared.
"""

import logging
import tempfile
from pathlib import Path
from typing import Any, Protocol

from app.acquisition import AcquisitionError, download_to_file
from app.captions import CaptionCue, build_product_ass
from app.templates import RenderTemplate
from app.product_content import ContentAngle, DISCLOSURE
from app.products import ProductFacts
from app.shorts_pipeline import (
    ArtifactStorage,
    ProgressReporter,
    ShortArtifact,
    ShortErrorCode,
    ShortPipelineError,
    ShortStage,
)
from app.tts import SpeechSynthesisError, SpeechSynthesizer
from app.video_processing import VideoInfo, VideoProcessingError


logger = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 25 * 1024 * 1024
GAP_SECONDS = 0.35
TAIL_SECONDS = 1.2


class ProductComposer(Protocol):
    def probe(self, media_path: Path) -> VideoInfo: ...

    def concat_audio(self, parts: list[Path], output_path: Path) -> None: ...

    def compose_product_short(
        self,
        image_path: Path,
        audio_path: Path,
        output_path: Path,
        *,
        duration_seconds: float,
        subtitles_path: Path | None = None,
    ) -> None: ...


def price_line(facts: ProductFacts) -> str | None:
    if facts.sales_price is None:
        return None
    line = f"{facts.sales_price:,}원"
    if facts.discount_rate:
        line = f"{facts.discount_rate}% 할인 · " + line
    if facts.origin_price is not None and facts.origin_price > facts.sales_price:
        line += f" (정가 {facts.origin_price:,}원)"
    return line


class ProductShortPipeline:
    def __init__(
        self,
        synthesizer: SpeechSynthesizer,
        composer: ProductComposer,
        storage: ArtifactStorage,
        *,
        max_seconds: float = 60,
    ) -> None:
        self._synthesizer = synthesizer
        self._composer = composer
        self._storage = storage
        self._max_seconds = max_seconds

    @property
    def storage(self) -> ArtifactStorage:
        return self._storage

    def run(
        self,
        *,
        job_id: str,
        facts: ProductFacts,
        angle: ContentAngle,
        template: RenderTemplate,
        report: ProgressReporter,
        cta_url: str | None = None,
    ) -> ShortArtifact:
        try:
            return self._run(
                job_id=job_id, facts=facts, angle=angle, template=template, report=report,
                cta_url=cta_url,
            )
        except ShortPipelineError:
            raise
        except AcquisitionError as exc:
            raise ShortPipelineError(
                ShortErrorCode.SOURCE_DOWNLOAD_FAILED, str(exc), retryable=exc.retryable
            ) from exc
        except SpeechSynthesisError as exc:
            raise ShortPipelineError(
                ShortErrorCode.TTS_FAILED, str(exc), retryable=exc.retryable
            ) from exc
        except VideoProcessingError as exc:
            logger.warning("Product short composition failed: %s", exc)
            raise ShortPipelineError(
                ShortErrorCode.FFMPEG_FAILED, "상품 쇼츠를 합성하지 못했습니다."
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected product pipeline failure", extra={"job_id": job_id})
            raise ShortPipelineError(
                ShortErrorCode.INTERNAL_ERROR, "상품 쇼츠 생성 중 오류가 발생했습니다."
            ) from exc

    def _run(
        self,
        *,
        job_id: str,
        facts: ProductFacts,
        angle: ContentAngle,
        template: RenderTemplate,
        report: ProgressReporter,
        cta_url: str | None,
    ) -> ShortArtifact:
        sentences = [angle.hook, *angle.script, angle.cta]
        with tempfile.TemporaryDirectory(
            prefix=f"shortsflow-product-{job_id}-", ignore_cleanup_errors=True
        ) as temp:
            temp_path = Path(temp)
            image_path = temp_path / "product.jpg"
            report(ShortStage.DOWNLOADING, 3)
            download_to_file(
                facts.image_url,
                image_path,
                max_bytes=MAX_IMAGE_BYTES,
                timeout_seconds=60,
                progress=lambda value: report(ShortStage.DOWNLOADING, 3 + value * 7 // 100),
            )

            # One TTS clip per sentence; measured durations drive the caption cues.
            report(ShortStage.PROCESSING, 12)
            parts: list[Path] = []
            cues: list[CaptionCue] = []
            cursor = 0.0
            for index, sentence in enumerate(sentences):
                part = temp_path / f"line-{index:02d}.mp3"
                self._synthesizer.synthesize(sentence, part)
                duration = self._composer.probe(part).duration_seconds
                cues.append(
                    CaptionCue(start_seconds=cursor, end_seconds=cursor + duration, text=sentence)
                )
                parts.append(part)
                cursor += duration + GAP_SECONDS
                report(ShortStage.PROCESSING, 12 + round(40 * (index + 1) / len(sentences)))
            total = cursor - GAP_SECONDS + TAIL_SECONDS
            if total > self._max_seconds:
                raise ShortPipelineError(
                    ShortErrorCode.INVALID_TIME_RANGE,
                    f"대본이 너무 길어 {round(total)}초가 됩니다. 최대 {int(self._max_seconds)}초로 줄여 주세요.",
                    retryable=False,
                )

            # Silence between lines comes from the gap in cue timing; the joined track
            # is padded to the full clip length by the video's -t.
            audio_path = temp_path / "narration.m4a"
            padded_parts = self._with_gaps(parts, temp_path)
            self._composer.concat_audio(padded_parts, audio_path)
            report(ShortStage.PROCESSING, 58)

            subtitles_path = temp_path / "product.ass"
            cta_text = angle.cta if not cta_url else f"{angle.cta} · 링크는 설명란에"
            subtitles_path.write_text(
                build_product_ass(
                    cues,
                    template=template,
                    total_seconds=total,
                    title=facts.title,
                    price_line=price_line(facts),
                    cta=cta_text,
                    disclosure=DISCLOSURE,
                ),
                encoding="utf-8",
            )
            output_path = temp_path / "output.mp4"
            self._composer.compose_product_short(
                image_path,
                audio_path,
                output_path,
                duration_seconds=total,
                subtitles_path=subtitles_path,
            )
            output_bytes = output_path.stat().st_size
            info = self._composer.probe(output_path)

            report(ShortStage.UPLOADING, 88)
            try:
                stored = self._storage.store(
                    output_path,
                    key=f"shorts/{job_id}.mp4",
                    filename=f"cutpick-product-{facts.product_id}.mp4",
                )
            except Exception as exc:
                logger.exception("Product short upload failed", extra={"job_id": job_id})
                raise ShortPipelineError(
                    ShortErrorCode.STORAGE_UPLOAD_FAILED,
                    "완성된 쇼츠를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.",
                ) from exc

        return ShortArtifact(
            provider=facts.provider,
            storage=stored.storage,
            storage_key=stored.key,
            download_url=stored.download_url,
            preview_url=stored.preview_url,
            local_path=str(stored.local_path) if stored.local_path else None,
            expires_at=stored.expires_at,
            template_id=template.value,
            captions_applied=len(cues),
            source_title=facts.title,
            source_duration_seconds=info.duration_seconds,
            source_width=info.width,
            source_height=info.height,
            output_bytes=output_bytes,
        )

    def _with_gaps(self, parts: list[Path], temp_path: Path) -> list[Path]:
        """Insert a short silence clip between spoken lines so cues match the audio."""
        if len(parts) <= 1:
            return parts
        silence = temp_path / "gap.mp3"
        self._make_silence(silence)
        interleaved: list[Path] = []
        for index, part in enumerate(parts):
            if index:
                interleaved.append(silence)
            interleaved.append(part)
        return interleaved

    def _make_silence(self, destination: Path) -> None:
        make = getattr(self._composer, "make_silence", None)
        if make is None:
            raise VideoProcessingError("무음 구간을 만들 수 없습니다.")
        make(destination, seconds=GAP_SECONDS)


def render_input_for(
    facts: ProductFacts,
    angle: ContentAngle,
    *,
    cta_url: str | None,
    content_generator: str,
) -> dict[str, Any]:
    return {
        "kind": "product",
        "facts": facts.model_dump(mode="json"),
        "angle": angle.model_dump(mode="json"),
        "cta_url": cta_url,
        "content_generator": content_generator,
    }
