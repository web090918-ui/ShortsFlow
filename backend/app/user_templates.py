"""Templates a creator makes from a screenshot of a Short they like.

A screenshot is not copied; a vision model measures it (where the picture band
sits, how the headline and caption are styled, what chrome exists) and the result
is expressed in the same ``CaptionStyle`` vocabulary as the built-in presets, so
every custom template renders through the existing ASS builder. Measurements are
snapped to a few geometry presets, which is why the creator does not have to edit
anything afterwards: the output is always a valid, good-looking composition.
"""

import json
import logging
import re
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.captions import (
    BLACK,
    BRAND,
    TEMPLATE_STYLES,
    WHITE,
    CaptionStyle,
    ass_color,
    template_catalog_entry,
)
from app.config import Settings
from app.templates import RenderTemplate, STAGE_PICTURE_HEIGHTS


logger = logging.getLogger(__name__)
BASE_TEMPLATE = RenderTemplate.CAPTION_ACCENT
MAX_TEMPLATES_PER_USER = 10
MAX_IMAGE_BYTES = 6 * 1024 * 1024
HEX = r"^#[0-9A-Fa-f]{6}$"
_DATA_URL = re.compile(r"^data:image/(png|jpeg|jpg|webp);base64,[A-Za-z0-9+/=\s]+$")


class TemplateExtractionError(RuntimeError):
    """The screenshot could not be turned into a template."""


class TemplateSpec(BaseModel):
    """What the extractor reports about a screenshot, in plain terms."""

    name: str = Field(default="내 템플릿", max_length=40)
    layout: Literal["STAGE", "FILL", "FIT"] = "STAGE"
    stage_color: str = Field(default="#000000", pattern=HEX)
    # Picture band edges as fractions of the frame height.
    picture_top: float = Field(default=0.19, ge=0.0, le=1.0)
    picture_bottom: float = Field(default=0.81, ge=0.0, le=1.0)
    headline_color: str = Field(default="#FFFFFF", pattern=HEX)
    # Colour of the emphasised headline line or word; None uses the render's brand colour.
    headline_accent: str | None = Field(default=None, pattern=HEX)
    headline_box: bool = False
    headline_align: Literal["center", "left"] = "center"
    caption: bool = True
    caption_box: bool = False
    caption_color: str = Field(default="#FFFFFF", pattern=HEX)
    caption_box_color: str = Field(default="#000000", pattern=HEX)
    caption_size: Literal["small", "medium", "large"] = "medium"
    hashtags: bool = False
    channel_line: bool = False
    tagline: str | None = Field(default=None, max_length=24)
    header_band: str | None = Field(default=None, max_length=24)


def snap_picture_height(spec: TemplateSpec) -> int:
    measured = max(0.0, spec.picture_bottom - spec.picture_top) * 1920
    return min(STAGE_PICTURE_HEIGHTS, key=lambda preset: abs(preset - measured))


def style_from_spec(spec: TemplateSpec) -> CaptionStyle:
    """Translate a spec into a renderable style on top of the plain caption preset."""
    base = TEMPLATE_STYLES[BASE_TEMPLATE]
    caption_size = {"small": 50, "medium": 60, "large": 72}[spec.caption_size]
    picture_height = snap_picture_height(spec)
    preview: dict[str, str] = {
        "caption": "plain" if spec.caption else "none",
        "weight": "800",
        "color": spec.caption_color,
        "stage": spec.stage_color,
        "headlineBox": "true" if spec.headline_box else "false",
    }
    if spec.caption_box:
        preview["background"] = spec.caption_box_color
    if spec.headline_accent:
        preview["headlineAccent"] = spec.headline_accent
    if spec.tagline:
        preview["tagline"] = spec.tagline
    if spec.header_band:
        preview["headerBand"] = spec.header_band
    return replace(
        base,
        name=spec.name,
        description="스크린샷에서 만든 내 템플릿",
        tag="내 템플릿",
        font_size=caption_size,
        primary=ass_color(spec.caption_color),
        outline=ass_color(spec.caption_box_color) if spec.caption_box else BLACK,
        back=ass_color(spec.caption_box_color).replace("&H00", "&HA0", 1) if spec.caption_box else "&H80000000",
        border_style=3 if spec.caption_box else 1,
        outline_width=12 if spec.caption_box else 4,
        highlight=None,
        emphasize_longest=False,
        show_caption=spec.caption,
        positionable=True,
        stage_color=spec.stage_color,
        text_color=ass_color(spec.headline_color),
        headline_accent=ass_color(spec.headline_accent) if spec.headline_accent else BRAND,
        headline_box=spec.headline_box,
        headline_align_left=spec.headline_align == "left",
        channel_line=spec.channel_line,
        tagline=spec.tagline,
        header_band=spec.header_band,
        kicker=None,
        hashtags=spec.hashtags,
        picture_height=picture_height,
        listed=False,
        preview=preview,
    )


class UserTemplate(BaseModel):
    id: str
    user_id: UUID | None
    spec: TemplateSpec
    created_at: datetime

    def style(self) -> CaptionStyle:
        return style_from_spec(self.spec)

    def catalog_entry(self) -> dict[str, Any]:
        entry = template_catalog_entry(self.id, self.style())
        entry["custom"] = True
        entry["base"] = BASE_TEMPLATE.value
        entry["layout"] = self.spec.layout
        return entry


class UserTemplateRepository(Protocol):
    def save(self, template: UserTemplate) -> UserTemplate: ...

    def get(self, template_id: str) -> UserTemplate | None: ...

    def list_for_user(self, user_id: UUID | None) -> list[UserTemplate]: ...

    def delete(self, template_id: str) -> None: ...


class InMemoryUserTemplateRepository:
    def __init__(self) -> None:
        self._items: dict[str, UserTemplate] = {}

    def save(self, template: UserTemplate) -> UserTemplate:
        self._items[template.id] = template
        return template

    def get(self, template_id: str) -> UserTemplate | None:
        return self._items.get(template_id)

    def list_for_user(self, user_id: UUID | None) -> list[UserTemplate]:
        return sorted(
            (t for t in self._items.values() if t.user_id == user_id),
            key=lambda t: t.created_at,
        )

    def delete(self, template_id: str) -> None:
        self._items.pop(template_id, None)


class FirestoreUserTemplateRepository:
    def __init__(self, client: Any, collection: str = "user_templates") -> None:
        self._collection = client.collection(collection)

    def save(self, template: UserTemplate) -> UserTemplate:
        self._collection.document(template.id).set(template.model_dump(mode="json"))
        return template

    def get(self, template_id: str) -> UserTemplate | None:
        snapshot = self._collection.document(template_id).get()
        return UserTemplate.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def list_for_user(self, user_id: UUID | None) -> list[UserTemplate]:
        from google.cloud.firestore_v1 import FieldFilter

        query = self._collection.where(
            filter=FieldFilter("user_id", "==", str(user_id) if user_id else None)
        )
        items = [UserTemplate.model_validate(doc.to_dict()) for doc in query.stream()]
        return sorted(items, key=lambda t: t.created_at)

    def delete(self, template_id: str) -> None:
        self._collection.document(template_id).delete()


def repository_from_settings(settings: Settings) -> UserTemplateRepository:
    if settings.job_repository_backend == "memory":
        return InMemoryUserTemplateRepository()
    from google.cloud import firestore

    return FirestoreUserTemplateRepository(
        firestore.Client(project=settings.gcp_project_id, database=settings.firestore_database)
    )


class TemplateExtractor(Protocol):
    def extract(self, image_data_url: str) -> TemplateSpec: ...


EXTRACTION_PROMPT = """You measure a screenshot of a vertical short-form video (9:16) and
describe its layout so it can be rebuilt as a caption template. Report JSON only:

{"name": "<short Korean name, max 20 chars>",
 "layout": "STAGE" if the source video sits in a band with solid colour above and
           below, "FILL" if the video fills the whole frame, "FIT" if blurred copies of
           the video fill the top and bottom,
 "stage_color": "#RRGGBB" of the solid area above/below the video (black if FILL/FIT),
 "picture_top": fraction (0-1) of the frame height where the source video starts,
 "picture_bottom": fraction where it ends,
 "headline_color": "#RRGGBB" main colour of the big title text,
 "headline_accent": "#RRGGBB" of the differently coloured title line or word, or null,
 "headline_box": true if the title sits on an opaque box,
 "headline_align": "center" or "left",
 "caption": true if a spoken-word subtitle is visible,
 "caption_box": true if the subtitle sits on an opaque box,
 "caption_color": "#RRGGBB", "caption_box_color": "#RRGGBB",
 "caption_size": "small" | "medium" | "large" relative to the frame width,
 "hashtags": true if hashtags are drawn as part of the layout,
 "channel_line": true if a channel name is drawn as part of the layout,
 "tagline": short pill text above the title or null,
 "header_band": full-width band text at the very top or null}

Ignore logos, watermarks, stickers, emoji and sound-effect text in the picture; they
are not part of the template. Measure fractions from the top edge of the frame.
Never invent text that is not visible."""


class OpenAITemplateExtractor:
    def __init__(self, client: Any, *, model: str) -> None:
        self._client = client
        self._model = model

    def extract(self, image_data_url: str) -> TemplateSpec:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": EXTRACTION_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Measure this screenshot."},
                            {"type": "image_url", "image_url": {"url": image_data_url, "detail": "high"}},
                        ],
                    },
                ],
            )
            content = response.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("Template extraction request failed", exc_info=exc)
            raise TemplateExtractionError("스크린샷을 분석하지 못했습니다. 잠시 후 다시 시도해 주세요.") from exc
        try:
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise ValueError("not an object")
            return TemplateSpec.model_validate({k: v for k, v in payload.items() if v is not None or k in ("headline_accent", "tagline", "header_band")})
        except Exception as exc:
            logger.warning("Template extraction returned an unusable payload: %s", content[:200])
            raise TemplateExtractionError("스크린샷에서 템플릿 정보를 읽지 못했습니다. 다른 캡처로 다시 시도해 주세요.") from exc


def validate_image_data_url(value: str) -> str:
    if not _DATA_URL.match(value or ""):
        raise TemplateExtractionError("PNG, JPEG 또는 WebP 이미지를 올려 주세요.")
    if len(value) > MAX_IMAGE_BYTES * 4 // 3 + 64:
        raise TemplateExtractionError("이미지가 너무 큽니다. 6MB 이하로 올려 주세요.")
    return value


def create_template(
    repository: UserTemplateRepository,
    extractor: TemplateExtractor,
    *,
    user_id: UUID | None,
    image_data_url: str,
    name: str | None = None,
) -> UserTemplate:
    validate_image_data_url(image_data_url)
    if len(repository.list_for_user(user_id)) >= MAX_TEMPLATES_PER_USER:
        raise TemplateExtractionError(f"내 템플릿은 최대 {MAX_TEMPLATES_PER_USER}개까지 저장할 수 있습니다.")
    spec = extractor.extract(image_data_url)
    if name and name.strip():
        spec = spec.model_copy(update={"name": name.strip()[:40]})
    template = UserTemplate(
        id=f"user-{uuid4().hex[:12]}",
        user_id=user_id,
        spec=spec,
        created_at=datetime.now(timezone.utc),
    )
    return repository.save(template)


def resolve_style(
    repository: UserTemplateRepository,
    *,
    template: RenderTemplate,
    custom_template_id: str | None,
    user_id: UUID | None,
) -> CaptionStyle | None:
    """The style a job should render with: a user's template, or None for a built-in."""
    if not custom_template_id:
        return None
    custom = repository.get(custom_template_id)
    if custom is None or custom.user_id != user_id:
        return None
    return custom.style()
