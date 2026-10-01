"""Task 10: selling points, three content angles, and Hook / Script / CTA.

The generator is a small boundary so the model vendor can change. Output is
constrained to a fixed JSON shape and validated before it reaches rendering.
"""

import json
import logging
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.products import ProductFacts


logger = logging.getLogger(__name__)
CONTENT_VERSION = "product_v1"
DISCLOSURE = "이 영상은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
MAX_SCRIPT_SENTENCES = 8


class ContentAngle(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    hook: str = Field(min_length=1)
    script: list[str] = Field(min_length=1, max_length=MAX_SCRIPT_SENTENCES)
    cta: str = Field(min_length=1)


class ProductContent(BaseModel):
    generator: str
    version: str = CONTENT_VERSION
    selling_points: list[str]
    angles: list[ContentAngle]
    disclosure: str = DISCLOSURE
    # Suggested upload metadata the creator can edit; the title is also the headline.
    title: str | None = None
    description: str | None = None


class ContentGenerationError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class ProductContentGenerator(Protocol):
    def generate(self, facts: ProductFacts, *, notes: str | None = None) -> ProductContent: ...


SYSTEM_PROMPT = """You write Korean short-form product videos (YouTube Shorts, 30-45 seconds)
for an affiliate creator. You receive verified product facts. Never invent specs,
reviews, ratings, or claims that are not in the facts; you may phrase benefits that
follow directly from them (e.g. a label-free bottle is easier to recycle).

Return JSON only:
{
  "selling_points": ["...", "...", "..."],
  "angles": [
    {"id": "angle_1", "name": "짧은 앵글 이름", "summary": "이 앵글이 노리는 시청자와 감정, 한 문장",
     "hook": "첫 2초에 말할 한 문장 (질문이나 숫자로 시작)",
     "script": ["말할 문장 1", "말할 문장 2", "... 5~7개, 각 문장 25자 이내, 구어체, 존댓말"],
     "cta": "마지막 한 문장: 링크 안내 (예: 자세한 건 링크에서 확인하세요)"}
    , 2 more angles with different id, framing and emotion
  ]
}
Angles must be distinct: for example price/deal, practical daily use, and a
persona-driven story. Keep every sentence natural to read aloud by TTS. Do not
include the affiliate disclosure; it is added separately.

Also add two top-level fields:
- "title": a Shorts headline of at most 30 characters with the key phrase in
  square brackets, e.g. "코카콜라 30캔이 [13,200원]"; it is drawn on the video.
- "description": one or two sentences for the upload description (at most 150
  characters) followed by two or three hashtags. Do not include the disclosure."""


def build_user_prompt(facts: ProductFacts, notes: str | None) -> str:
    price_line = []
    if facts.sales_price is not None:
        price_line.append(f"판매가 {facts.sales_price:,}원")
    if facts.origin_price is not None:
        price_line.append(f"정가 {facts.origin_price:,}원")
    if facts.discount_rate:
        price_line.append(f"할인율 {facts.discount_rate}%")
    lines = [
        f"상품명: {facts.title}",
        "가격: " + (", ".join(price_line) if price_line else "알 수 없음"),
        "확인된 사실:",
        *[f"- {fact}" for fact in facts.facts],
    ]
    if facts.group:
        lines.append(f"- 판매 그룹: {facts.group}")
    if facts.description:
        lines.append(f"크리에이터가 적은 상품 설명: {facts.description[:600]}")
    if notes:
        lines.append(f"크리에이터 메모: {notes.strip()[:500]}")
    return "\n".join(lines)


def _clean_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    lines = [" ".join(line.split()) for line in value.replace("\r", "").split("\n")]
    cleaned = "\n".join(line for line in lines if line).strip().strip('"\u201c\u201d')
    return cleaned[:limit].rstrip() or None


def suggest_title(facts: ProductFacts) -> str:
    """Headline without a model: short name, price in brackets when known."""
    name = facts.title.split(",")[0].strip()
    name = name if len(name) <= 22 else name[:21].rstrip() + "\u2026"
    if facts.sales_price is not None:
        return f"{name}\n[{facts.sales_price:,}원]"
    return f"[{name}]"


def suggest_description(facts: ProductFacts) -> str:
    bits = [facts.title]
    if facts.sales_price is not None:
        bits.append(f"{facts.sales_price:,}원")
    if facts.discount_rate:
        bits.append(f"{facts.discount_rate}% 할인")
    return " · ".join(bits) + " 자세한 내용은 링크에서 확인하세요. #쇼츠 #추천템 #득템"


def _clean_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = [" ".join(str(item).split()) for item in value if str(item).strip()]
    return cleaned[:limit]


class OpenAIProductContentGenerator:
    def __init__(self, client: Any, *, model: str) -> None:
        self._client = client
        self._model = model

    def generate(self, facts: ProductFacts, *, notes: str | None = None) -> ProductContent:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(facts, notes)},
                ],
            )
            content = response.choices[0].message.content
        except Exception as exc:
            logger.warning("Product content request failed", exc_info=exc)
            status_code = getattr(exc, "status_code", None)
            raise ContentGenerationError(
                "콘텐츠 생성 요청에 실패했습니다"
                + (f" (HTTP {status_code})" if status_code else "")
                + f": {' '.join(str(exc).split())[:160]}",
                retryable=status_code not in {400, 401, 403, 404},
            ) from exc
        try:
            payload = json.loads(content or "")
        except json.JSONDecodeError as exc:
            raise ContentGenerationError("콘텐츠 생성 응답을 해석하지 못했습니다.") from exc
        if not isinstance(payload, dict):
            raise ContentGenerationError("콘텐츠 생성 응답 형식이 올바르지 않습니다.")

        angles: list[ContentAngle] = []
        for index, raw in enumerate(payload.get("angles") or [], start=1):
            if not isinstance(raw, dict):
                continue
            script = _clean_list(raw.get("script"), limit=MAX_SCRIPT_SENTENCES)
            hook = " ".join(str(raw.get("hook") or "").split())
            cta = " ".join(str(raw.get("cta") or "").split())
            if not script or not hook or not cta:
                continue
            angles.append(
                ContentAngle(
                    id=str(raw.get("id") or f"angle_{index}"),
                    name=" ".join(str(raw.get("name") or f"앵글 {index}").split()),
                    summary=" ".join(str(raw.get("summary") or "").split()) or hook,
                    hook=hook,
                    script=script,
                    cta=cta,
                )
            )
        if len(angles) < 3:
            raise ContentGenerationError("콘텐츠 앵글 3개를 만들지 못했습니다. 다시 시도해 주세요.")
        return ProductContent(
            generator=f"openai:{self._model}",
            selling_points=_clean_list(payload.get("selling_points"), limit=5) or facts.facts[:3],
            angles=angles[:3],
            title=_clean_text(payload.get("title"), 100) or suggest_title(facts),
            description=_clean_text(payload.get("description"), 500) or suggest_description(facts),
        )


def product_content_generator_from_settings(settings: Any) -> ProductContentGenerator:
    if settings.openai_api_key is None:
        return TemplateProductContentGenerator()
    from openai import OpenAI

    return OpenAIProductContentGenerator(
        OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            project=settings.openai_project,
            timeout=120,
            max_retries=1,
        ),
        model=settings.openai_ranking_model,
    )


class TemplateProductContentGenerator:
    """Development stand-in without an OpenAI key: deterministic angles from facts."""

    def generate(self, facts: ProductFacts, *, notes: str | None = None) -> ProductContent:
        price = f"{facts.sales_price:,}원" if facts.sales_price is not None else "특가"
        saving = (
            f"{facts.origin_price - facts.sales_price:,}원"
            if facts.origin_price is not None and facts.sales_price is not None
            else None
        )
        deal = ContentAngle(
            id="angle_deal",
            name="가격 앵글",
            summary="가격에 민감한 시청자에게 할인 폭을 먼저 보여 줍니다.",
            hook=f"{facts.title.split(',')[0]}, 지금 {price}이면 어떤가요?",
            script=[
                f"{facts.title}입니다.",
                *( [f"정가보다 {saving} 저렴하게 살 수 있어요."] if saving else [] ),
                *( [f"할인율은 {facts.discount_rate}%입니다."] if facts.discount_rate else [] ),
                "필요하셨다면 지금이 담아 두기 좋은 타이밍이에요.",
            ],
            cta="자세한 가격은 링크에서 확인하세요.",
        )
        daily = ContentAngle(
            id="angle_daily",
            name="일상 활용 앵글",
            summary="매일 쓰는 장면을 보여 주며 편의성을 강조합니다.",
            hook="집에 이거 떨어지면 은근히 불편하죠?",
            script=[
                f"{facts.title.split(',')[0]}을 넉넉히 쟁여 두면 편해요.",
                "필요할 때 바로 꺼내 쓸 수 있고요.",
                "대량 구성이라 한 번에 해결됩니다.",
            ],
            cta="구성과 가격은 링크에서 확인해 주세요.",
        )
        story = ContentAngle(
            id="angle_story",
            name="상황 앵글",
            summary="특정 상황을 그려 공감으로 시작합니다.",
            hook="주말 손님 오는데 마실 것 준비하셨어요?",
            script=[
                f"이럴 때 {facts.title.split(',')[0]} 한 박스면 든든하죠.",
                *( [f"지금은 {price}에 살 수 있습니다."] if facts.sales_price is not None else [] ),
                "미리 준비해 두면 마음이 편해요.",
            ],
            cta="링크에서 바로 확인하세요.",
        )
        return ProductContent(
            generator="template",
            selling_points=facts.facts[:3] or [facts.title],
            angles=[deal, daily, story],
            title=suggest_title(facts),
            description=suggest_description(facts),
        )
