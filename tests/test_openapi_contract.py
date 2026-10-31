"""Contract test: the checked-in OpenAPI schema must match the live app."""

import json
from pathlib import Path

from rfq_assistant.api.app import app

OPENAPI_PATH = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"


def test_checked_in_openapi_matches_live_app():
    assert OPENAPI_PATH.exists(), (
        "frontend/openapi.json is missing. Run "
        "`python -m rfq_assistant.scripts.export_openapi`."
    )
    checked_in = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert app.openapi() == checked_in, (
        "frontend/openapi.json is stale. Run "
        "`python -m rfq_assistant.scripts.export_openapi` and commit the result."
    )
