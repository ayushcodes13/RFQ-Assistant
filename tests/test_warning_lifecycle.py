"""Regression coverage for reviewer warning cleanup and editable-field audits."""

import importlib
from pathlib import Path

from fastapi.testclient import TestClient

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository


def test_resolving_vague_reference_clears_warning_and_audits_material_edits(
    monkeypatch, tmp_path
):
    api = importlib.import_module("rfq_assistant.api.app")
    catalog = CatalogRepository()
    catalog.replace_csv(
        (
            Path(__file__).resolve().parent.parent
            / "fixtures/catalogs/industrial_components_sample_catalog.csv"
        ).read_bytes()
    )
    manager = CaseManager(catalog, storage=DocumentStorage(tmp_path / "uploads"))
    monkeypatch.setattr(api, "case_manager", manager)
    monkeypatch.setattr(api, "ASYNC_INGEST_ENABLED", False)
    client = TestClient(api.app)

    created = client.post(
        "/api/rfqs",
        data={"pasted_text": "Please quote 4 units of the sensor from last time."},
    )
    assert created.status_code == 200
    case_id = created.json()["case_id"]
    lines = client.get(f"/api/rfqs/{case_id}/lines").json()
    line = lines[0]
    assert "UNKNOWN_PART_REFERENCE" in {
        warning["code"] for warning in line["extraction_warnings"]
    }

    matched = client.patch(
        f"/api/rfqs/{case_id}/lines/{line['line_id']}",
        json={
            "expected_version": line["version"],
            "requested_mpn": "E2E-X7D1-N",
            "requested_manufacturer": "Omron",
        },
    )
    assert matched.status_code == 200
    matched_line = matched.json()
    assert matched_line["match_status"] == "EXACT_MATCH"
    assert matched_line["selected_catalog_sku"] == "SKU-OMR-001"
    assert "UNKNOWN_PART_REFERENCE" not in {
        warning["code"] for warning in matched_line["extraction_warnings"]
    }

    edited = client.patch(
        f"/api/rfqs/{case_id}/lines/{line['line_id']}",
        json={
            "expected_version": matched_line["version"],
            "unit": "BOX",
            "description": "Shielded proximity sensor",
            "notes": "Confirmed with the synthetic customer",
        },
    )
    assert edited.status_code == 200

    events_response = client.get(f"/api/rfqs/{case_id}/audit")
    assert events_response.status_code == 200
    field_events = {
        event["field_name"]: event
        for event in events_response.json()
        if event["line_id"] == line["line_id"]
        and event["field_name"] in {"unit", "description", "notes"}
    }
    assert set(field_events) == {"unit", "description", "notes"}
    assert field_events["unit"]["old_value"] == "EA"
    assert field_events["unit"]["new_value"] == "BOX"
    assert field_events["description"]["old_value"] == line["description"]
    assert field_events["description"]["new_value"] == "Shielded proximity sensor"
    assert field_events["notes"]["old_value"] == "Vague customer reference"
    assert field_events["notes"]["new_value"] == "Confirmed with the synthetic customer"
    assert all(
        event["actor"] == "Local Pilot Operator" for event in field_events.values()
    )
