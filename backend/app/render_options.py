"""Read-only catalog of caption templates and frame layouts for the pickers.

The frontend renders its own preview (source thumbnail plus sample text styled
from the ``preview`` hints) so adding a template here is enough to ship it.
"""

from typing import Any

from fastapi import APIRouter

from app.captions import layout_catalog, template_catalog

router = APIRouter(tags=["templates"])


@router.get("/templates")
def list_templates() -> dict[str, list[dict[str, Any]]]:
    return {"templates": template_catalog(), "layouts": layout_catalog()}
