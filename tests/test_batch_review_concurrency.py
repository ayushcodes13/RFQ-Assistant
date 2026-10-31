"""API regressions for stale batch-review snapshots and no-op line edits."""

import csv
import importlib
import io

from fastapi.testclient import TestClient

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.schemas.models import CatalogItem


def _manager_case(tmp_path, row_count=12):
    catalog = CatalogRepository()
    rows = []
    for index in range(row_count):
        mpn = f"BATCH-{index:04d}"
        catalog.add_item(CatalogItem(
            internal_sku=f"BATCH-SKU-{index:04d}",
            manufacturer="Synthetic Controls",
            manufacturer_part_number=mpn,
            description=f"Synthetic part {index}",
        ))
        rows.append([mpn, "Synthetic Controls", 2, f"Synthetic part {index}", "EA"])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["MPN", "Manufacturer", "Qty", "Description", "UOM"])
    writer.writerows(rows)
    manager = CaseManager(catalog, storage=DocumentStorage(tmp_path / "files"))
    case = manager.create_case_from_upload("synthetic-batch.csv", output.getvalue().encode())
    return manager, case


def _version_map(lines):
    return {line["line_id"]: line["version"] for line in lines}


def test_stale_batch_review_returns_409_without_changing_line(monkeypatch, tmp_path):
    api = importlib.import_module("rfq_assistant.api.app")

    manager, case = _manager_case(tmp_path)
    monkeypatch.setattr(api, "case_manager", manager)
    client = TestClient(api.app)
    lines = client.get(f"/api/rfqs/{case.case_id}/lines").json()
    plan = client.get(f"/api/rfqs/{case.case_id}/review-plan").json()
    target_ids = plan["sample_line_ids"][:2]
    targets = [
        next(line for line in lines if line["line_id"] == target_id)
        for target_id in target_ids
    ]
    stale_target = targets[1]

    changed = client.patch(
        f"/api/rfqs/{case.case_id}/lines/{stale_target['line_id']}",
        json={"expected_version": stale_target["version"], "quantity": 77},
    )
    assert changed.status_code == 200
    stale_request = client.post(
        f"/api/rfqs/{case.case_id}/review",
        json={
            "line_ids": target_ids,
            "expected_versions": {line["line_id"]: line["version"] for line in targets},
            "decision": "APPROVED",
        },
    )

    after = {
        line["line_id"]: line
        for line in client.get(f"/api/rfqs/{case.case_id}/lines").json()
        if line["line_id"] in target_ids
    }
    assert stale_request.status_code == 409
    assert after[stale_target["line_id"]]["quantity"] == 77
    assert after[stale_target["line_id"]]["version"] == changed.json()["version"]
    assert all(line["review_decision"] == "PENDING" for line in after.values())


def test_stale_approve_remaining_returns_409_without_approving_any_row(
    monkeypatch, tmp_path
):
    api = importlib.import_module("rfq_assistant.api.app")

    manager, case = _manager_case(tmp_path)
    monkeypatch.setattr(api, "case_manager", manager)
    client = TestClient(api.app)
    plan = client.get(f"/api/rfqs/{case.case_id}/review-plan").json()
    lines = client.get(f"/api/rfqs/{case.case_id}/lines").json()
    sample_versions = {
        line["line_id"]: line["version"]
        for line in lines if line["line_id"] in plan["sample_line_ids"]
    }
    sample_approval = client.post(
        f"/api/rfqs/{case.case_id}/review",
        json={
            "line_ids": plan["sample_line_ids"],
            "expected_versions": sample_versions,
            "decision": "APPROVED",
        },
    )
    assert sample_approval.status_code == 200

    # Capture the visible snapshot, then let another reviewer change a row.
    snapshot = client.get(f"/api/rfqs/{case.case_id}/lines").json()
    remaining_id = plan["remaining_line_ids"][0]
    remaining = next(line for line in snapshot if line["line_id"] == remaining_id)
    changed = client.patch(
        f"/api/rfqs/{case.case_id}/lines/{remaining_id}",
        json={"expected_version": remaining["version"], "quantity": 77},
    )
    assert changed.status_code == 200
    stale_approval = client.post(
        f"/api/rfqs/{case.case_id}/review-plan/approve-remaining",
        json={"expected_versions": _version_map(snapshot)},
    )

    after = client.get(f"/api/rfqs/{case.case_id}/lines").json()
    assert stale_approval.status_code == 409
    assert all(
        line["review_decision"] == "PENDING"
        for line in after if line["line_id"] in plan["remaining_line_ids"]
    )


def test_noop_line_update_does_not_advance_version_or_add_audit(monkeypatch, tmp_path):
    api = importlib.import_module("rfq_assistant.api.app")

    manager, case = _manager_case(tmp_path, row_count=1)
    monkeypatch.setattr(api, "case_manager", manager)
    client = TestClient(api.app)
    line = client.get(f"/api/rfqs/{case.case_id}/lines").json()[0]
    audit_before = client.get(f"/api/rfqs/{case.case_id}/audit").json()

    response = client.patch(
        f"/api/rfqs/{case.case_id}/lines/{line['line_id']}",
        json={"expected_version": line["version"]},
    )

    audit_after = client.get(f"/api/rfqs/{case.case_id}/audit").json()
    assert response.status_code == 200
    assert response.json()["version"] == line["version"]
    assert audit_after == audit_before
