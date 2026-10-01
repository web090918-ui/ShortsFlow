"""Catalog of caption templates and frame layouts for the pickers, plus a creator's
own templates made from screenshots.

The frontend renders its own preview (source thumbnail plus sample text styled
from the ``preview`` hints) so adding a template here is enough to ship it.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import UserRecord, current_user, require_user
from app.captions import (
    BRAND_SWATCHES,
    DEFAULT_BRAND_COLOR,
    caption_position_catalog,
    layout_catalog,
    template_catalog,
)
from app.config import Settings, get_settings
from app.user_templates import (
    OpenAITemplateExtractor,
    TemplateExtractionError,
    TemplateExtractor,
    UserTemplateRepository,
    create_template,
    repository_from_settings,
)


logger = logging.getLogger(__name__)
router = APIRouter(tags=["templates"])


def _extractor_from_settings(settings: Settings) -> TemplateExtractor | None:
    if settings.openai_api_key is None:
        return None
    from openai import OpenAI

    return OpenAITemplateExtractor(
        OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            project=settings.openai_project,
            timeout=90,
            max_retries=1,
        ),
        model=settings.openai_vision_model,
    )


settings = get_settings()
user_templates: UserTemplateRepository = repository_from_settings(settings)
template_extractor: TemplateExtractor | None = _extractor_from_settings(settings)


class TemplateFromImageRequest(BaseModel):
    # A data URL (data:image/png;base64,...) of the screenshot; 6 MB at most.
    image_data_url: str = Field(min_length=32, max_length=9 * 1024 * 1024)
    name: str | None = Field(default=None, max_length=40)


@router.get("/templates")
def list_templates(user: UserRecord | None = Depends(current_user)) -> dict[str, Any]:
    return {
        "templates": template_catalog(),
        "user_templates": [
            item.catalog_entry() for item in user_templates.list_for_user(user.id if user else None)
        ],
        "layouts": layout_catalog(),
        "caption_positions": caption_position_catalog(),
        "brand_colors": BRAND_SWATCHES,
        "default_brand_color": DEFAULT_BRAND_COLOR,
    }


@router.post("/templates/from-image", status_code=status.HTTP_201_CREATED)
def template_from_image(
    payload: TemplateFromImageRequest,
    user: UserRecord | None = Depends(require_user),
) -> dict[str, Any]:
    if template_extractor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="스크린샷 분석을 위해 SHORTSFLOW_OPENAI_API_KEY를 설정해야 합니다.",
        )
    try:
        template = create_template(
            user_templates,
            template_extractor,
            user_id=user.id if user else None,
            image_data_url=payload.image_data_url,
            name=payload.name,
        )
    except TemplateExtractionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return template.catalog_entry()


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: str, user: UserRecord | None = Depends(require_user)) -> None:
    template = user_templates.get(template_id)
    if template is None or template.user_id != (user.id if user else None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")
    user_templates.delete(template_id)
