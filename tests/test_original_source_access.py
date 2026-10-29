"""Synthetic source-file access tests for the reviewer workbench."""

import importlib

from fastapi.testclient import TestClient

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository


def test_original_source_is_case_scoped_and_not_cached(tmp_path, monkeypatch):
    api = importlib.import_module("rfq_assistant.api.app")
    manager = CaseManager(catalog=CatalogRepository(), storage=DocumentStorage(tmp_path / "source"))
    monkeypatch.setattr(api, "case_manager", manager)
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)

    original = b"10 pcs Schneider Electric LC1D09BD"
    case = manager.create_case_from_upload(filename="source.txt", content=original)
    client = TestClient(api.app)

    response = client.get(f"/api/rfqs/{case.case_id}/source")
    assert response.status_code == 200
    assert response.content == original
    assert "text/plain" in response.headers["content-type"]
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"

    assert client.get("/api/rfqs/RFQ-NOT-EXIST/source").status_code == 404
    manager.delete_case(case.case_id)
    assert client.get(f"/api/rfqs/{case.case_id}/source").status_code == 404


def test_protected_source_rejects_anonymous_and_allows_viewer(tmp_path, monkeypatch):
    api = importlib.import_module("rfq_assistant.api.app")
    manager = CaseManager(catalog=CatalogRepository(), storage=DocumentStorage(tmp_path / "source"))
    monkeypatch.setattr(api, "case_manager", manager)
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    monkeypatch.setenv("PILOT_API_KEYS", "synthetic-test-viewer-secret-001:viewer:Viewer")
    case = manager.create_case_from_text("10 pcs Schneider Electric LC1D09BD")
    client = TestClient(api.app)

    assert client.get(f"/api/rfqs/{case.case_id}/source").status_code == 401
    response = client.get(
        f"/api/rfqs/{case.case_id}/source",
        headers={"X-API-Key": "synthetic-test-viewer-secret-001"},
    )
    assert response.status_code == 200
    assert b"LC1D09BD" in response.content
