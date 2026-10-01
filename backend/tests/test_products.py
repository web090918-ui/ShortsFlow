import pytest
from fastapi.testclient import TestClient

import app.sources as sources_module
from app.main import app
from app.product_content import (
    ContentGenerationError,
    OpenAIProductContentGenerator,
    TemplateProductContentGenerator,
)
from app.products import (
    CoupangPartnersLinkProvider,
    ProductSourceError,
    coupang_image_at,
    prepare_product,
)


client = TestClient(app)

PARTNERS_URL = (
    "https://partners.coupang.com/#affiliate/ws/linkgeneration/PRODUCT/7310929139/25822417217"
    "?group=goldbox&product%5Btype%5D=PRODUCT&product%5BitemId%5D=25822417217"
    "&product%5BproductId%5D=7310929139&product%5BvendorItemId%5D=88377301380"
    "&product%5Bimage%5D=https%3A%2F%2Fthumbnail5.coupangcdn.com%2Fthumbnails%2Fremote%2F212x212ex"
    "%2Fimage%2Fretail%2Fimages%2F1435598150504811-d5c1cf7b.jpg"
    "&product%5Btitle%5D=%EC%BD%94%EC%B9%B4%EC%BD%9C%EB%9D%BC%20%EC%98%A4%EB%A6%AC%EC%A7%80%EB%84%90"
    "%20%EB%AC%B4%EB%9D%BC%EB%B2%A8%2C%20370ml%2C%2024%EA%B0%9C"
    "&product%5BdiscountRate%5D=37&product%5BoriginPrice%5D=28600&product%5BsalesPrice%5D=17990"
    "&product%5BdeliveryBadgeImage%5D=https%3A%2F%2Fimage8.coupangcdn.com%2Fimage%2Frds%2Fbadge.png"
    "&product%5Btravel%5D=false"
)


def test_coupang_partners_link_is_parsed_into_product_facts() -> None:
    prepared = CoupangPartnersLinkProvider().prepare(PARTNERS_URL)

    product = prepared.metadata["product"]
    assert product["provider"] == "coupang_partners"
    assert product["product_id"] == "7310929139"
    assert product["item_id"] == "25822417217"
    assert product["vendor_item_id"] == "88377301380"
    assert product["title"] == "코카콜라 오리지널 무라벨, 370ml, 24개"
    assert product["origin_price"] == 28600
    assert product["sales_price"] == 17990
    assert product["discount_rate"] == 37
    assert product["group"] == "goldbox"
    assert product["image_url"].startswith(
        "https://thumbnail5.coupangcdn.com/thumbnails/remote/1000x1000ex/"
    )
    assert product["thumbnail_url"].endswith("212x212ex/image/retail/images/1435598150504811-d5c1cf7b.jpg")
    assert product["product_url"] == (
        "https://www.coupang.com/vp/products/7310929139?itemId=25822417217&vendorItemId=88377301380"
    )
    assert "판매가 17,990원" in product["facts"]
    assert "정가 28,600원에서 10,610원 절약" in product["facts"]
    assert "37% 할인" in product["facts"]
    assert "골드박스 특가 (기간 한정)" in product["facts"]
    assert prepared.processing_reference["product_id"] == "7310929139"


def test_coupang_image_size_substitution() -> None:
    assert coupang_image_at(
        "https://thumbnail5.coupangcdn.com/thumbnails/remote/212x212ex/image/a.jpg", "492x492ex"
    ) == "https://thumbnail5.coupangcdn.com/thumbnails/remote/492x492ex/image/a.jpg"
    # Non-thumbnail URLs are left alone.
    assert coupang_image_at("https://image7.coupangcdn.com/image/retail/a.jpg") == (
        "https://image7.coupangcdn.com/image/retail/a.jpg"
    )


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.coupang.com/vp/products/7310929139?itemId=1", "파트너스 링크"),
        ("https://link.coupang.com/a/abcdef", "단축 링크"),
        ("https://partners.coupang.com/#affiliate/ws/linkgeneration/PRODUCT/1?group=x", "상품명과 이미지"),
        ("https://smartstore.naver.com/x/products/1", "지원하지 않는"),
    ],
)
def test_unsupported_or_incomplete_product_urls_explain_what_to_do(url, expected) -> None:
    with pytest.raises(ProductSourceError, match=expected):
        prepare_product(url)


def test_rejects_non_coupang_image_hosts() -> None:
    url = PARTNERS_URL.replace(
        "https%3A%2F%2Fthumbnail5.coupangcdn.com", "https%3A%2F%2Fevil.example.com"
    )
    with pytest.raises(ProductSourceError):
        CoupangPartnersLinkProvider().prepare(url)


def test_product_source_prepares_from_partners_link_via_api() -> None:
    response = client.post("/sources?prepare=true", json={"url": PARTNERS_URL})

    assert response.status_code == 201
    source = response.json()
    assert source["type"] == "PRODUCT"
    assert source["status"] == "READY"
    assert source["metadata"]["product"]["title"].startswith("코카콜라")
    assert "processing_reference" not in source


def test_product_source_prepare_failure_is_actionable() -> None:
    response = client.post(
        "/sources?prepare=true", json={"url": "https://www.coupang.com/vp/products/7310929139"}
    )

    assert response.status_code == 502
    assert "파트너스 링크" in response.json()["detail"]


def test_template_content_generator_produces_three_distinct_angles() -> None:
    facts = CoupangPartnersLinkProvider().prepare(PARTNERS_URL)
    from app.products import ProductFacts

    content = TemplateProductContentGenerator().generate(
        ProductFacts.model_validate(facts.metadata["product"])
    )

    assert content.generator == "template"
    assert len(content.angles) == 3
    assert len({angle.id for angle in content.angles}) == 3
    for angle in content.angles:
        assert angle.hook and angle.cta and angle.script
    assert "17,990원" in content.angles[0].hook
    assert content.disclosure.startswith("이 영상은 쿠팡 파트너스")


class FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        message = type("Message", (), {"content": self.content})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


def _openai(content: str):
    client = type("C", (), {})()
    completions = FakeCompletions(content)
    client.chat = type("Chat", (), {"completions": completions})()
    return client, completions


def test_openai_content_generator_validates_shape() -> None:
    import json

    from app.products import ProductFacts

    facts = ProductFacts.model_validate(
        CoupangPartnersLinkProvider().prepare(PARTNERS_URL).metadata["product"]
    )
    payload = {
        "selling_points": ["37% 할인", "무라벨"],
        "angles": [
            {"id": f"angle_{i}", "name": f"앵글 {i}", "summary": "요약", "hook": f"훅 {i}",
             "script": ["문장 하나", "문장 둘"], "cta": "링크에서 확인하세요"}
            for i in range(1, 4)
        ],
    }
    client, completions = _openai(json.dumps(payload))

    content = OpenAIProductContentGenerator(client, model="m").generate(facts, notes="메모")

    assert content.generator == "openai:m"
    assert [a.id for a in content.angles] == ["angle_1", "angle_2", "angle_3"]
    assert "크리에이터 메모: 메모" in completions.kwargs["messages"][1]["content"]
    assert "판매가 17,990원" in completions.kwargs["messages"][1]["content"]

    short_client, _ = _openai(json.dumps({"angles": payload["angles"][:2]}))
    with pytest.raises(ContentGenerationError):
        OpenAIProductContentGenerator(short_client, model="m").generate(facts)


def test_product_content_endpoint_caches_angles(monkeypatch) -> None:
    monkeypatch.setattr(
        sources_module, "product_content_generator", TemplateProductContentGenerator()
    )
    source = client.post("/sources?prepare=true", json={"url": PARTNERS_URL}).json()

    first = client.post(f"/sources/{source['id']}/product-content", json={})
    assert first.status_code == 200
    content = first.json()["metadata"]["product_content"]
    assert len(content["angles"]) == 3

    second = client.post(f"/sources/{source['id']}/product-content", json={})
    assert second.json()["metadata"]["product_content"] == content

    youtube = client.post("/sources", json={"url": "https://youtu.be/abc12345678"}).json()
    denied = client.post(f"/sources/{youtube['id']}/product-content", json={})
    assert denied.status_code == 409


def test_manual_product_input_builds_facts_and_a_ready_source() -> None:
    from app.products import ManualProductInput, manual_product_facts

    facts = manual_product_facts(
        ManualProductInput(
            title="  수제 그래놀라  500g ",
            sales_price=12900,
            origin_price=18000,
            description="국내산 귀리로 만들었어요. 설탕 대신 꿀을 썼습니다.\n아침 대용으로 딱.",
            image_urls=["https://images.example.com/granola.jpg", "upload://uploads/img-a.png"],
            product_url="https://smartstore.naver.com/x/products/1",
        )
    )

    assert facts.provider == "manual" and facts.title == "수제 그래놀라 500g"
    assert facts.discount_rate == 28
    assert facts.image_url == "https://images.example.com/granola.jpg"
    assert facts.all_image_urls == ["https://images.example.com/granola.jpg", "upload://uploads/img-a.png"]
    assert facts.facts[:3] == ["판매가 12,900원", "정가 18,000원에서 5,100원 절약", "28% 할인"]
    assert "국내산 귀리로 만들었어요." in facts.facts and "아침 대용으로 딱." in facts.facts
    assert facts.description.startswith("국내산 귀리로")

    with pytest.raises(ProductSourceError):
        manual_product_facts(
            ManualProductInput(title="x", image_urls=["ftp://images.example.com/a.jpg"])
        )


def test_manual_product_source_and_picture_upload_via_api(tmp_path, monkeypatch) -> None:
    import app.sources as sources_module
    from app.shorts_pipeline import LocalArtifactStorage

    monkeypatch.setattr(sources_module, "upload_storage", LocalArtifactStorage(tmp_path))

    registered = client.post(
        "/sources/product-images",
        json={"filename": "photo.PNG", "content_type": "image/png", "size_bytes": 3},
    )
    assert registered.status_code == 201
    upload = registered.json()
    assert upload["image_url"].startswith("upload://uploads/img-") and upload["image_url"].endswith(".png")
    assert upload["upload"]["mode"] == "direct"

    # Before the bytes arrive the Source cannot be created.
    pending = client.post(
        "/sources/product",
        json={"title": "사진으로 만든 상품", "image_urls": [upload["image_url"]]},
    )
    assert pending.status_code == 409

    stored = client.put(upload["upload"]["url"], content=b"png")
    assert stored.status_code == 204

    created = client.post(
        "/sources/product",
        json={
            "title": "사진으로 만든 상품",
            "sales_price": 9900,
            "description": "직접 찍은 사진 세 장으로 소개합니다.",
            "image_urls": [upload["image_url"]],
        },
    )
    assert created.status_code == 201
    source = created.json()
    assert source["type"] == "PRODUCT" and source["status"] == "READY"
    assert source["metadata"]["product"]["provider"] == "manual"
    assert source["metadata"]["product"]["image_urls"] == [upload["image_url"]]
    assert "processing_reference" not in source

    bad = client.post("/sources/product", json={"title": "", "image_urls": []})
    assert bad.status_code == 422


def test_content_generators_suggest_title_and_description() -> None:
    from app.product_content import TemplateProductContentGenerator, suggest_title

    facts = _facts() if "_facts" in globals() else None
    if facts is None:
        from app.products import ProductFacts

        facts = ProductFacts(
            provider="manual",
            product_id="x",
            title="코카콜라 오리지널, 190ml, 30개",
            sales_price=13200,
            discount_rate=39,
            image_url="https://images.example.com/c.jpg",
            product_url="",
        )
    content = TemplateProductContentGenerator().generate(facts)

    assert content.title == suggest_title(facts) == "코카콜라 오리지널\n[13,200원]"
    assert content.description and "#쇼츠" in content.description and "13,200원" in content.description
