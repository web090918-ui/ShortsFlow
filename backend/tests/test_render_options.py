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
    assert payload["templates"][0]["id"] == "HEADLINE_YELLOW"
    assert "NEON_GLOW" not in [item["id"] for item in payload["templates"]]
    assert [item["id"] for item in payload["layouts"]] == ["STAGE", "FIT", "FILL"]
    assert {layout.value for layout in RenderLayout} == {"STAGE", "FIT", "FILL"}
    impact = next(item for item in payload["templates"] if item["id"] == "IMPACT_YELLOW")
    assert impact["karaoke"] is True
    assert impact["preview"]["accent"] == "#FFD23F"
    assert impact["name"] == TEMPLATE_STYLES[RenderTemplate.IMPACT_YELLOW].name
    for item in payload["templates"]:
        assert item["name"] and item["description"] and item["tag"]
