from fastapi.testclient import TestClient

from app.captions import TEMPLATE_STYLES
from app.main import app
from app.templates import RenderLayout, RenderTemplate

client = TestClient(app)


def test_templates_endpoint_lists_every_template_and_layout() -> None:
    response = client.get("/templates")

    assert response.status_code == 200
    payload = response.json()
    listed = [t.value for t in RenderTemplate if TEMPLATE_STYLES[t].listed]
    assert [item["id"] for item in payload["templates"]] == listed
    assert payload["templates"][0]["id"] == "CAPTION_POP"
    assert "NEON_GLOW" not in [item["id"] for item in payload["templates"]]
    assert [item["id"] for item in payload["caption_positions"]] == ["BOTTOM", "MIDDLE"]
    assert payload["default_brand_color"] == "#4FE1E1"
    assert {swatch["hex"] for swatch in payload["brand_colors"]} >= {"#4FE1E1", "#FFD23F"}
    paper = next(item for item in payload["templates"] if item["id"] == "PAPER")
    assert paper["preview"]["stage"] == "#F5F1E8" and paper["preview"]["channel"] == "true"
    assert [item["id"] for item in payload["layouts"]] == ["STAGE", "FIT", "FILL"]
    assert {layout.value for layout in RenderLayout} == {"STAGE", "FIT", "FILL"}
    accent = next(item for item in payload["templates"] if item["id"] == "CAPTION_ACCENT")
    assert accent["karaoke"] is True
    assert accent["preview"]["caption"] == "karaoke" and accent["preview"]["positionable"] == "true"
    assert "positionable" not in payload["templates"][3]["preview"]  # PAPER keeps the band
    assert accent["name"] == TEMPLATE_STYLES[RenderTemplate.CAPTION_ACCENT].name
    for item in payload["templates"]:
        assert item["name"] and item["description"] and item["tag"]
