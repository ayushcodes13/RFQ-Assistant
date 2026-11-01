"""A reviewer can recover a missing row without fabricating source citation."""

import importlib
from pathlib import Path

from fastapi.testclient import TestClient

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.schemas.models import CatalogItem


def test_failed_text_case_can_recover_with_manual_pending_line(monkeypatch, tmp_path):
    api = importlib.import_module("rfq_assistant.api.app")
    catalog = CatalogRepository()
    catalog.add_item(CatalogItem(
        internal_sku="SYN-OMR-RELAY",
        manufacturer="Omron",
        manufacturer_part_number="G2R-1-S",
        description="Synthetic relay",
        stock_qty=50,
    ))
    manager = CaseManager(catalog, storage=DocumentStorage(tmp_path / "uploads"))
    monkeypatch.setattr(api, "case_manager", manager)
    monkeypatch.setattr(api, "ASYNC_INGEST_ENABLED", False)
    client = TestClient(api.app)

    created = client.post(
        "/api/rfqs",
        data={"pasted_text": "Subject: Request for quotation\nDate: 2026-11-01"},
    )
    assert created.status_code == 200
    case_id = created.json()["case_id"]
    assert created.json()["status"] == "FAILED"
    assert client.get(f"/api/rfqs/{case_id}/lines").json() == []

    added = client.post(
        f"/api/rfqs/{case_id}/lines",
        json={
            "source_text": "the small blue relay from last month, about 20",
            "description": "small blue relay",
            "quantity": 20,
            "unit": "EA",
        },
    )
    assert added.status_code == 201, added.text
    line = added.json()
    assert line["source_locator"]["file_name"] == "Manual operator entry"
    assert line["source_locator"]["source_file_id"] is None
    assert line["match_status"] == "NO_MATCH"
    assert line["review_decision"] == "PENDING"
    assert line["extraction_status"] == "NEEDS_CORRECTION"
    assert line["field_provenance"]["quantity"]["origin"] == "HUMAN"
    assert line["field_provenance"]["quantity"]["validation_status"] == "manual_entry_unverified"
    assert any(warning["code"] == "MANUAL_ENTRY_SOURCE_REVIEW_REQUIRED" for warning in line["extraction_warnings"])

    corrected = client.patch(
        f"/api/rfqs/{case_id}/lines/{line['line_id']}",
        json={
            "expected_version": line["version"],
            "requested_manufacturer": "Omron",
            "requested_mpn": "G2R-1-S",
            "actor": "spoofed actor",
        },
    )
    assert corrected.status_code == 200
    line = corrected.json()
    assert line["match_status"] == "EXACT_MATCH"
    assert line["selected_catalog_sku"] == "SYN-OMR-RELAY"
    assert line["extraction_status"] == "EXTRACTED"
    assert line["review_decision"] == "PENDING"

    approved = client.patch(
        f"/api/rfqs/{case_id}/lines/{line['line_id']}",
        json={"expected_version": line["version"], "review_decision": "APPROVED"},
    )
    assert approved.status_code == 200
    events = client.get(f"/api/rfqs/{case_id}/audit").json()
    manual_add = next(event for event in events if event["action"] == "LINE_ADDED_MANUALLY")
    assert manual_add["actor"] == "Local Pilot Operator"
    assert manual_add["notes"] == "Manually entered line added; verify it against the original buyer source."
