import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app import render_options as render_options_module
from app import shorts as shorts_module
from app import processing_jobs as jobs_module
from app.captions import TEMPLATE_STYLES, build_ass
from app.main import app
from app.templates import RenderLayout, RenderTemplate
from app.user_templates import (
    InMemoryUserTemplateRepository,
    OpenAITemplateExtractor,
    TemplateExtractionError,
    TemplateSpec,
    create_template,
    resolve_style,
    snap_picture_height,
    style_from_spec,
)

client = TestClient(app)
PNG = "data:image/png;base64," + "iVBORw0KGgo" * 8


class FakeExtractor:
    def __init__(self, spec: TemplateSpec | None = None) -> None:
        self.spec = spec or TemplateSpec(
            name="솔로파티",
            stage_color="#000000",
            picture_top=0.2,
            picture_bottom=0.81,
            headline_accent="#FF6A00",
            caption_box=True,
            hashtags=True,
        )
        self.calls = 0

    def extract(self, image_data_url: str) -> TemplateSpec:
        self.calls += 1
        return self.spec


def test_spec_translates_into_a_renderable_style_with_snapped_geometry() -> None:
    spec = FakeExtractor().spec
    assert snap_picture_height(spec) == 1180
    style = style_from_spec(spec)

    assert style.name == "솔로파티" and style.tag == "내 템플릿" and style.listed is False
    assert style.picture_height == 1180
    assert style.headline_accent == "&H00006AFF"  # #FF6A00 as ASS BGR
    assert style.border_style == 3 and style.hashtags is True and style.highlight is None
    assert style.preview["picture"] if "picture" in style.preview else True

    # A near-16:9 picture snaps to the small band; a middle one to 900.
    assert snap_picture_height(TemplateSpec(picture_top=0.34, picture_bottom=0.66)) == 608
    assert snap_picture_height(TemplateSpec(picture_top=0.27, picture_bottom=0.73)) == 900

    # The style renders through the normal builder in place of the preset.
    document = build_ass(
        [],
        template=RenderTemplate.CAPTION_ACCENT,
        clip_start_seconds=0,
        clip_end_seconds=10,
        layout=RenderLayout.STAGE,
        title="[설레는] 솔로파티",
        description="#이상준쇼 #이상준",
        style=style,
    )
    assert "Style: Default,NanumSquareRound,60,&H00FFFFFF" in document
    assert "#이상준쇼 #이상준" in document


def test_create_template_validates_the_image_and_caps_the_count() -> None:
    repo = InMemoryUserTemplateRepository()
    extractor = FakeExtractor()
    user_id = uuid4()

    created = create_template(repo, extractor, user_id=user_id, image_data_url=PNG, name="  내 스타일 ")
    assert created.id.startswith("user-") and created.spec.name == "내 스타일"
    assert repo.list_for_user(user_id) == [created]
    assert resolve_style(repo, template=RenderTemplate.CAPTION_POP, custom_template_id=created.id, user_id=user_id).picture_height == 1180
    # Someone else's template, or an unknown id, falls back to the preset.
    assert resolve_style(repo, template=RenderTemplate.CAPTION_POP, custom_template_id=created.id, user_id=uuid4()) is None
    assert resolve_style(repo, template=RenderTemplate.CAPTION_POP, custom_template_id="nope", user_id=user_id) is None

    try:
        create_template(repo, extractor, user_id=user_id, image_data_url="data:text/plain;base64,aGk=")
    except TemplateExtractionError as exc:
        assert "PNG" in str(exc)
    else:
        raise AssertionError("non-image data URL accepted")

    for _ in range(9):
        create_template(repo, extractor, user_id=user_id, image_data_url=PNG)
    try:
        create_template(repo, extractor, user_id=user_id, image_data_url=PNG)
    except TemplateExtractionError as exc:
        assert "최대 10개" in str(exc)
    else:
        raise AssertionError("eleventh template accepted")


def test_openai_extractor_parses_json_and_reports_bad_payloads() -> None:
    class Completions:
        def __init__(self, content):
            self.content = content
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            message = type("M", (), {"content": self.content})()
            return type("R", (), {"choices": [type("C", (), {"message": message})()]})()

    good = Completions(json.dumps({"name": "x", "picture_top": 0.2, "picture_bottom": 0.8, "headline_accent": None, "tagline": None, "header_band": None}))
    client_stub = type("Client", (), {"chat": type("Chat", (), {"completions": good})()})()
    spec = OpenAITemplateExtractor(client_stub, model="vision-test").extract(PNG)
    assert spec.name == "x" and spec.headline_accent is None
    assert good.kwargs["messages"][1]["content"][1]["image_url"]["url"] == PNG

    bad = Completions("not json")
    client_stub = type("Client", (), {"chat": type("Chat", (), {"completions": bad})()})()
    try:
        OpenAITemplateExtractor(client_stub, model="vision-test").extract(PNG)
    except TemplateExtractionError:
        pass
    else:
        raise AssertionError("bad payload accepted")


def test_templates_api_creates_lists_and_deletes_user_templates(monkeypatch) -> None:
    repo = InMemoryUserTemplateRepository()
    monkeypatch.setattr(render_options_module, "user_templates", repo)
    monkeypatch.setattr(render_options_module, "template_extractor", FakeExtractor())
    monkeypatch.setattr(shorts_module, "user_templates", repo)
    monkeypatch.setattr(jobs_module, "user_templates", repo)

    created = client.post("/templates/from-image", json={"image_data_url": PNG})
    assert created.status_code == 201, created.text
    entry = created.json()
    assert entry["custom"] is True and entry["base"] == "CAPTION_ACCENT"
    assert entry["preview"]["picture"] == "0.615" and entry["preview"]["stage"] == "#000000"
    assert entry["tag"] == "내 템플릿"

    listed = client.get("/templates").json()
    assert [item["id"] for item in listed["user_templates"]] == [entry["id"]]
    assert all(item["preview"]["picture"] for item in listed["templates"])

    deleted = client.delete(f"/templates/{entry['id']}")
    assert deleted.status_code == 204
    assert client.get("/templates").json()["user_templates"] == []
    assert client.delete(f"/templates/{entry['id']}").status_code == 404


def test_templates_api_rejects_bad_images_and_missing_extractor(monkeypatch) -> None:
    monkeypatch.setattr(render_options_module, "user_templates", InMemoryUserTemplateRepository())
    monkeypatch.setattr(render_options_module, "template_extractor", FakeExtractor())
    bad = client.post("/templates/from-image", json={"image_data_url": "data:text/plain;base64," + "aGk=" * 10})
    assert bad.status_code == 422 and "PNG" in bad.json()["detail"]

    monkeypatch.setattr(render_options_module, "template_extractor", None)
    assert client.post("/templates/from-image", json={"image_data_url": PNG}).status_code == 503


def test_built_in_catalog_still_lists_every_template() -> None:
    payload = client.get("/templates").json()
    listed = [t.value for t in RenderTemplate if TEMPLATE_STYLES[t].listed]
    assert [item["id"] for item in payload["templates"]] == listed
