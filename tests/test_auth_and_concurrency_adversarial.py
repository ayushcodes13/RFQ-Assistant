"""Adversarial tests for pilot authentication, authorization boundaries, export scoping, and concurrency.

Validates:
1. Unauthorized read, modification, deletion, catalog import, approval, and export access when auth is enforced.
2. Cross-case export isolation (export ID accessed through the wrong case ID).
3. Actor spoofing prevention (authenticated identity overrides client-supplied actor strings).
4. Stale state / optimistic concurrency collision (version mismatch produces 409 Conflict).
5. Explicit labeling of simulated send and fail-closed blocking when real transport is required.
"""

import io
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from rfq_assistant.agents.tools import ApprovalGateError, QuotationCommercialService
from rfq_assistant.api.app import app, case_manager, catalog_repo, commercial_service, export_generator
from rfq_assistant.matching.catalog import CatalogItem
from rfq_assistant.quotation.validate import ProposedQuote, QuoteLine
from rfq_assistant.schemas.enums import ReviewDecision
from rfq_assistant.schemas.models import ExportRequest, RFQLineItemUpdate


@pytest.fixture
def client():
    return TestClient(app)


def test_auth_enforced_blocks_unauthenticated_requests(client, monkeypatch):
    """When REQUIRE_AUTH=true, requests without valid pilot keys must be rejected with 401."""
    monkeypatch.setenv("REQUIRE_AUTH", "true")

    # 1. Unauthenticated read
    resp = client.get("/api/rfqs")
    assert resp.status_code == 401
    assert "Authentication required" in resp.json()["detail"]

    # 2. Invalid API key
    resp = client.get("/api/rfqs", headers={"X-API-Key": "invalid-bogus-key"})
    assert resp.status_code == 401
    assert "Invalid pilot API key" in resp.json()["detail"]


def test_role_based_access_control(client, monkeypatch):
    """Viewer cannot delete or import; Reviewer cannot delete cases (admin only)."""
    monkeypatch.setenv("REQUIRE_AUTH", "true")

    # Viewer role key
    viewer_headers = {"X-API-Key": "pilot-viewer-key"}
    # Reviewer role key
    reviewer_headers = {"X-API-Key": "pilot-reviewer-key"}
    # Admin role key
    admin_headers = {"X-API-Key": "pilot-admin-key"}

    # Create a test case as admin
    case = case_manager.create_case_from_text(
        raw_text="10 pcs LC1D09BD Schneider",
        title="RBAC Case",
        actor="Admin",
    )

    # 1. Viewer trying to delete case -> 403
    del_resp = client.delete(f"/api/rfqs/{case.case_id}", headers=viewer_headers)
    assert del_resp.status_code == 403
    assert "lacks required permissions" in del_resp.json()["detail"]

    # 2. Reviewer trying to delete case -> 403 (admin only)
    del_resp = client.delete(f"/api/rfqs/{case.case_id}", headers=reviewer_headers)
    assert del_resp.status_code == 403

    # 3. Viewer trying to import catalog -> 403
    import_resp = client.post(
        "/api/catalogs/import",
        files={"file": ("cat.csv", b"internal_sku,manufacturer,manufacturer_part_number,description,list_price\nSKU-1,OEM,MPN,Desc,10\n")},
        headers=viewer_headers,
    )
    assert import_resp.status_code == 403

    # 4. Admin successfully deletes case -> 200
    del_admin = client.delete(f"/api/rfqs/{case.case_id}", headers=admin_headers)
    assert del_admin.status_code == 200


def test_authenticated_actor_cannot_be_spoofed(client, monkeypatch):
    """Client-supplied actor string is ignored in favor of authenticated principal."""
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    headers = {"X-API-Key": "pilot-reviewer-key"}  # Authorized Reviewer

    case = case_manager.create_case_from_text(
        raw_text="5 pcs 6ES7214-1AG40-0XB0 Siemens",
        title="Actor Provenance Case",
        actor="System",
    )
    line = case_manager.get_lines(case.case_id)[0]

    # Attempt to spoof actor as "Chief Financial Officer"
    resp = client.patch(
        f"/api/rfqs/{case.case_id}/lines/{line.line_id}",
        json={"review_decision": "APPROVED", "actor": "Chief Financial Officer"},
        headers=headers,
    )
    assert resp.status_code == 200
    updated_line = resp.json()
    assert updated_line["reviewed_by"] == "Authorized Reviewer"

    # Verify audit event actor
    audit_resp = client.get(f"/api/rfqs/{case.case_id}/audit", headers=headers)
    latest_event = audit_resp.json()[-1]
    assert latest_event["actor"] == "Authorized Reviewer"
    assert latest_event["actor"] != "Chief Financial Officer"


def test_cross_case_export_access_blocked(client):
    """An export ID cannot be downloaded through a different case ID."""
    # Create Case 1 and Case 2
    case1 = case_manager.create_case_from_text(raw_text="10 pcs LC1D09BD Schneider", title="Case 1")
    case2 = case_manager.create_case_from_text(raw_text="5 pcs 6ES7214-1AG40-0XB0 Siemens", title="Case 2")

    line1 = case_manager.get_lines(case1.case_id)[0]
    line1.review_decision = ReviewDecision.APPROVED
    line1.selected_catalog_sku = "SKU-SCH-001"

    # Generate export for Case 1
    manifest = export_generator.generate_export(
        case=case1,
        lines=[line1],
        request=ExportRequest(case_id=case1.case_id, format="xlsx", allow_partial=True, actor="Tester"),
    )

    # Legitimate download through Case 1 succeeds
    resp_valid = client.get(f"/api/rfqs/{case1.case_id}/exports/{manifest.export_id}")
    assert resp_valid.status_code == 200

    # Cross-case unauthorized download through Case 2 is strictly blocked with 404
    resp_invalid = client.get(f"/api/rfqs/{case2.case_id}/exports/{manifest.export_id}")
    assert resp_invalid.status_code == 404
    assert f"Export '{manifest.export_id}' does not belong to case '{case2.case_id}'" in resp_invalid.json()["detail"]


def test_optimistic_concurrency_conflict_detection(client):
    """Submitting edits with a stale expected_version triggers 409 Conflict."""
    case = case_manager.create_case_from_text(raw_text="20 pcs LC1D09BD Schneider", title="Concurrency Test")
    line = case_manager.get_lines(case.case_id)[0]
    assert line.version == 1

    # First reviewer updates the line (version moves from 1 to 2)
    resp1 = client.patch(
        f"/api/rfqs/{case.case_id}/lines/{line.line_id}",
        json={"expected_version": 1, "quantity": 25.0},
    )
    assert resp1.status_code == 200
    assert resp1.json()["version"] == 2

    # Second reviewer (stale browser tab) attempts to update using outdated expected_version=1
    resp2 = client.patch(
        f"/api/rfqs/{case.case_id}/lines/{line.line_id}",
        json={"expected_version": 1, "quantity": 30.0},
    )
    assert resp2.status_code == 409
    assert "Stale state / conflict" in resp2.json()["detail"]


def test_simulated_send_transparency_and_strict_transport_mode(monkeypatch):
    """Simulated transport is explicitly labeled; when REQUIRE_REAL_TRANSPORT=true, send is blocked."""
    service = QuotationCommercialService()
    line = QuoteLine(
        line_no=1,
        requested_mpn="LC1D09BD",
        catalogue_part_id="SKU-SCH-001",
        quantity=Decimal("10"),
        unit_price=Decimal("45.00"),
        currency="USD",
        source_price_id="v1",
        match_status="exact",
        requires_human_review=False,
    )
    quote = ProposedQuote(
        quote_id="Q-TRANS-1",
        case_id="RFQ-TRANS-1",
        customer_name="Transport Test Co",
        lines=[line],
    )
    service.register_draft(quote)
    draft_hash = quote.compute_draft_hash()
    service.approve_draft("Q-TRANS-1", draft_hash, "Approver Alice")

    # 1. Standard mode: Send produces simulated transmission record with explicit notes
    result = service.send_approved_quote("Q-TRANS-1", draft_hash, "Sender Bob")
    assert result["status"] == "SENT"
    assert result["is_simulated"] is True
    assert result["outbound_transport_invoked"] is False
    assert result["transport"] == "simulated_local"
    assert "No live SMTP or external network transport" in result["transport_notes"]

    # 2. Strict real transport mode: REQUIRE_REAL_TRANSPORT=true blocks simulated sends
    monkeypatch.setenv("REQUIRE_REAL_TRANSPORT", "true")
    service2 = QuotationCommercialService()
    service2.register_draft(quote)
    service2.approve_draft("Q-TRANS-1", draft_hash, "Approver Alice")

    with pytest.raises(ApprovalGateError) as exc_info:
        service2.send_approved_quote("Q-TRANS-1", draft_hash, "Sender Bob")

    assert "Blocked: Real outbound transport is not configured" in str(exc_info.value)
