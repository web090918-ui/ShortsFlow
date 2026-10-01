"""Product source providers (Task 10).

The first provider parses Coupang Partners link-generation URLs. Those URLs carry
the product facts in their query string, so no request to coupang.com is needed;
the public product page returns 403 to servers, which is why scraping is not the
MVP path. Other product sites need their own small provider behind the same
boundary.
"""

import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field


class ProductSourceError(Exception):
    """An actionable product preparation failure safe to return to the client."""


class ProductFacts(BaseModel):
    provider: str
    product_id: str
    item_id: str | None = None
    vendor_item_id: str | None = None
    title: str = Field(min_length=1)
    currency: str = "KRW"
    origin_price: int | None = None
    sales_price: int | None = None
    discount_rate: int | None = None
    image_url: str
    # Every picture for the slideshow (first == image_url); https or upload:// URLs.
    image_urls: list[str] = []
    thumbnail_url: str | None = None
    delivery_badge_url: str | None = None
    group: str | None = None
    product_url: str
    facts: list[str] = []
    # Free text the creator typed (manual input); feeds the AI, not the facts list.
    description: str | None = None

    @property
    def all_image_urls(self) -> list[str]:
        urls = [self.image_url, *self.image_urls]
        seen: list[str] = []
        for url in urls:
            if url and url not in seen:
                seen.append(url)
        return seen


MAX_PRODUCT_IMAGES = 3
MAX_DESCRIPTION_CHARS = 1000


class ManualProductInput(BaseModel):
    """What a creator types when no link can be read: name, price, blurb, pictures."""

    title: str = Field(min_length=1, max_length=120)
    sales_price: int | None = Field(default=None, ge=0, le=1_000_000_000)
    origin_price: int | None = Field(default=None, ge=0, le=1_000_000_000)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_CHARS)
    image_urls: list[str] = Field(min_length=1, max_length=MAX_PRODUCT_IMAGES)
    product_url: str | None = Field(default=None, max_length=2048)
    provider_label: str | None = Field(default=None, max_length=40)


def _manual_image(url: str) -> str:
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme == "upload" or (parsed.scheme == "https" and parsed.hostname):
        return cleaned
    raise ProductSourceError("이미지는 https 주소이거나 업로드한 파일이어야 합니다.")


def manual_product_facts(payload: ManualProductInput) -> ProductFacts:
    """Facts for a hand-entered product; the first image leads the slideshow."""
    images = [_manual_image(url) for url in payload.image_urls if url and url.strip()]
    if not images:
        raise ProductSourceError("상품 이미지를 1장 이상 넣어 주세요.")
    title = " ".join(payload.title.split())
    description = " ".join(payload.description.split()) if payload.description else None
    sales, origin = payload.sales_price, payload.origin_price
    discount = None
    if sales is not None and origin is not None and origin > sales > 0:
        discount = round((origin - sales) * 100 / origin)
    facts: list[str] = []
    if sales is not None:
        facts.append(f"판매가 {sales:,}원")
    if discount:
        facts.append(f"정가 {origin:,}원에서 {origin - sales:,}원 절약")
        facts.append(f"{discount}% 할인")
    if description:
        # Up to three short statements from the blurb, so the AI has concrete claims.
        for sentence in re.split(r"(?<=[.!?。])\s+|\n+", description):
            sentence = sentence.strip(" -•·")
            if 4 <= len(sentence) <= 80 and len(facts) < 6:
                facts.append(sentence)
    product_url = (payload.product_url or "").strip()
    if product_url and urlparse(product_url).scheme not in {"http", "https"}:
        raise ProductSourceError("상품 링크는 http(s) 주소여야 합니다.")
    return ProductFacts(
        provider="manual",
        product_id=re.sub(r"[^0-9A-Za-z]+", "-", title)[:40].strip("-").lower() or "manual",
        title=title,
        origin_price=origin,
        sales_price=sales,
        discount_rate=discount,
        image_url=images[0],
        image_urls=images,
        thumbnail_url=images[0],
        group=payload.provider_label,
        product_url=product_url,
        facts=facts,
        description=description,
    )


@dataclass(frozen=True)
class PreparedProductSource:
    metadata: dict[str, Any]
    processing_reference: dict[str, Any]


class ProductSourceProvider(Protocol):
    def supports(self, url: str) -> bool: ...

    def prepare(self, url: str) -> PreparedProductSource: ...


_COUPANG_THUMB_SIZE = re.compile(r"/thumbnails/remote/\d+x\d+(ex)?/")
COUPANG_IMAGE_SIZE = "1000x1000ex"


def coupang_image_at(url: str, size: str = COUPANG_IMAGE_SIZE) -> str:
    """Coupang CDN thumbnails encode their size in the path; ask for a larger one."""
    return _COUPANG_THUMB_SIZE.sub(f"/thumbnails/remote/{size}/", url, count=1)


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None


def _https_image(url: str | None) -> str | None:
    if not isinstance(url, str) or not url:
        return None
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname.endswith("coupangcdn.com"):
        return None
    return url


class CoupangPartnersLinkProvider:
    """Parses partners.coupang.com link-generation URLs and public product URLs."""

    name = "coupang_partners"

    def supports(self, url: str) -> bool:
        hostname = (urlparse(url).hostname or "").lower()
        return hostname in {"partners.coupang.com", "www.coupang.com", "coupang.com", "m.coupang.com", "link.coupang.com"}

    def prepare(self, url: str) -> PreparedProductSource:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if hostname == "partners.coupang.com":
            facts = self._from_partners_console(url)
        elif hostname in {"www.coupang.com", "coupang.com", "m.coupang.com"}:
            raise ProductSourceError(
                "쿠팡 상품 페이지는 서버에서 읽을 수 없습니다. 쿠팡 파트너스 링크 생성 화면의 "
                "URL(partners.coupang.com/#affiliate/ws/linkgeneration/...)을 붙여 주세요."
            )
        elif hostname == "link.coupang.com":
            raise ProductSourceError(
                "단축 링크(link.coupang.com)에는 상품 정보가 없습니다. 파트너스 링크 생성 화면의 "
                "URL을 붙이고, 단축 링크는 CTA 링크 칸에 입력해 주세요."
            )
        else:
            raise ProductSourceError("지원하지 않는 상품 사이트입니다.")
        return PreparedProductSource(
            metadata={"product": facts.model_dump(mode="json")},
            processing_reference={
                "provider": self.name,
                "product_id": facts.product_id,
                "item_id": facts.item_id,
                "vendor_item_id": facts.vendor_item_id,
            },
        )

    def _from_partners_console(self, url: str) -> ProductFacts:
        parsed = urlparse(url)
        fragment = parsed.fragment or ""
        route, _, query = fragment.partition("?")
        params = {key: values[0] for key, values in parse_qs(query).items() if values}
        if not params:
            # Some browsers place the query before the fragment.
            params = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}

        route_match = re.search(r"linkgeneration/PRODUCT/(\d+)(?:/(\d+))?", route)
        product_id = params.get("product[productId]") or (route_match.group(1) if route_match else None)
        item_id = params.get("product[itemId]") or (
            route_match.group(2) if route_match and route_match.group(2) else None
        )
        title = " ".join((params.get("product[title]") or "").split())
        image = _https_image(params.get("product[image]"))
        if not product_id or not title or not image:
            raise ProductSourceError(
                "파트너스 링크에서 상품명과 이미지를 찾지 못했습니다. 링크 생성 화면의 전체 URL을 "
                "그대로 붙여 주세요."
            )

        origin_price = _int(params.get("product[originPrice]"))
        sales_price = _int(params.get("product[salesPrice]"))
        discount_rate = _int(params.get("product[discountRate]"))
        vendor_item_id = params.get("product[vendorItemId]")
        product_url = f"https://www.coupang.com/vp/products/{product_id}"
        query_bits = []
        if item_id:
            query_bits.append(f"itemId={item_id}")
        if vendor_item_id:
            query_bits.append(f"vendorItemId={vendor_item_id}")
        if query_bits:
            product_url += "?" + "&".join(query_bits)

        facts = []
        if sales_price is not None:
            facts.append(f"판매가 {sales_price:,}원")
        if origin_price is not None and sales_price is not None and origin_price > sales_price:
            facts.append(f"정가 {origin_price:,}원에서 {origin_price - sales_price:,}원 절약")
        if discount_rate:
            facts.append(f"{discount_rate}% 할인")
        if params.get("product[group]") == "goldbox" or params.get("group") == "goldbox":
            facts.append("골드박스 특가 (기간 한정)")
        if params.get("product[deliveryBadgeImage]"):
            facts.append("빠른 배송 배지 상품")

        return ProductFacts(
            provider=self.name,
            product_id=str(product_id),
            item_id=str(item_id) if item_id else None,
            vendor_item_id=str(vendor_item_id) if vendor_item_id else None,
            title=title,
            origin_price=origin_price,
            sales_price=sales_price,
            discount_rate=discount_rate,
            image_url=coupang_image_at(image),
            image_urls=[coupang_image_at(image)],
            thumbnail_url=image,
            delivery_badge_url=_https_image(params.get("product[deliveryBadgeImage]")),
            group=params.get("group") or params.get("product[group]"),
            product_url=product_url,
            facts=facts,
        )


PRODUCT_PROVIDERS: list[ProductSourceProvider] = [CoupangPartnersLinkProvider()]


def prepare_product(url: str) -> PreparedProductSource:
    for provider in PRODUCT_PROVIDERS:
        if provider.supports(url):
            return provider.prepare(url)
    raise ProductSourceError(
        "아직 지원하지 않는 상품 사이트입니다. 현재는 쿠팡 파트너스 링크만 처리합니다."
    )
