"""Unit and API integration tests for catalog matching, collision detection, and audit trails."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from rfq_assistant.api.app import app, catalog_repo, case_manager
from rfq_assistant.matching import (
    ExactMatchEngine,
    normalize_manufacturer,
    normalize_mpn,
)
from rfq_assistant.schemas.enums import (
    AuditAction,
    CaseStatus,
    MatchStatus,
    ReviewDecision,
)
from rfq_assistant.schemas.models import (
    BatchReviewRequest,
    CatalogItem,
    RFQLineItemUpdate,
)

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT / "fixtures" / "rfq_samples"


class TestNormalizerAndMatching:
    """Verifies strict MPN and OEM normalization and exact match semantics."""

    def test_normalizer_preserves_suffixes(self):
        # Critical invariant: never collapse suffixes
        assert normalize_mpn("ABC-12") == "ABC-12"
        assert normalize_mpn("ABC-12A") == "ABC-12A"
        assert normalize_mpn("ABC-12-R2") == "ABC-12-R2"
        assert normalize_mpn("  lc1d09bd  ") == "LC1D09BD"

    def test_normalizer_handles_oem_aliases(self):
        assert normalize_manufacturer("Schneider") == "Schneider Electric"
        assert normalize_manufacturer("Square D") == "Schneider Electric"
        assert normalize_manufacturer("Siemens AG") == "Siemens"
        assert normalize_manufacturer("Eaton Cutler-Hammer") == "Eaton"
        assert normalize_manufacturer("Unknown OEM") == "Unknown OEM"

    def test_exact_match_success(self):
        engine = ExactMatchEngine(catalog_repo)
        res = engine.match_line("LC1D09BD", "Schneider Electric")
        assert res.match_status == MatchStatus.EXACT_MATCH
        assert res.selected_sku == "SKU-SCH-001"
        assert len(res.candidates) == 1
        assert res.candidates[0].catalog_item.internal_sku == "SKU-SCH-001"

    def test_suffix_precision_matching(self):
        engine = ExactMatchEngine(catalog_repo)
        res1 = engine.match_line("ABC-12", "Acme Industrial")
        assert res1.match_status == MatchStatus.EXACT_MATCH
        assert res1.selected_sku == "SKU-SUF-001"

        res2 = engine.match_line("ABC-12A", "Acme Industrial")
        assert res2.match_status == MatchStatus.EXACT_MATCH
        assert res2.selected_sku == "SKU-SUF-002"

        res3 = engine.match_line("ABC-12-R2", "Acme Industrial")
        assert res3.match_status == MatchStatus.EXACT_MATCH
        assert res3.selected_sku == "SKU-SUF-003"

    def test_cross_brand_collision_scenario3(self):
        # Scenario 3: Part number XG-42 requested with NO manufacturer specified
        engine = ExactMatchEngine(catalog_repo)
        res = engine.match_line("XG-42", requested_manufacturer=None)
        assert res.match_status == MatchStatus.COLLISION
        assert res.selected_sku is None
        assert len(res.candidates) == 2
        oems = {c.catalog_item.manufacturer for c in res.candidates}
        assert oems == {"Apex Automation", "Delta Electronics"}

    def test_no_match_unknown_part(self):
        engine = ExactMatchEngine(catalog_repo)
        res = engine.match_line("NONEXISTENT-999-XYZ", "Schneider Electric")
        assert res.match_status == MatchStatus.NO_MATCH
        assert res.selected_sku is None
        assert len(res.candidates) == 0


class TestCaseManagerAndAuditTrail:
    """Verifies case creation, line corrections, re-matching, and audit logging."""

    def test_create_case_and_audit(self):
        xlsx_path = SAMPLES_DIR / "industrial_control_bom_20lines.xlsx"
        case = case_manager.create_case_from_upload(
            filename="industrial_control_bom_20lines.xlsx",
            content=xlsx_path.read_bytes(),
            customer_label="Test Automation Corp",
            actor="Operator Bob",
        )

        assert case.line_count == 20
        assert case.status == CaseStatus.NEEDS_REVIEW

        # Audit trail must record creation and parse
        trail = case_manager.get_audit_trail(case.case_id)
        assert len(trail) >= 2
        actions = [e.action for e in trail]
        assert AuditAction.CASE_CREATED in actions
        assert AuditAction.PARSED in actions

        lines = case_manager.get_lines(case.case_id)
        line18 = [l for l in lines if l.line_number == 18][0]
        assert line18.quantity is None

        # Operator updates line 18 quantity
        updated = case_manager.update_line(
            case_id=case.case_id,
            line_id=line18.line_id,
            update=RFQLineItemUpdate(expected_version=line18.version,
                quantity=100.0,
                actor="Operator Bob",
                reviewer_notes="Confirmed quantity with customer",
            ),
        )
        assert updated.quantity == 100.0

        # Verify audit log captured quantity modification
        trail_after = case_manager.get_audit_trail(case.case_id)
        edit_event = next(e for e in trail_after if e.line_id == line18.line_id)
        assert edit_event.action == AuditAction.LINE_EDITED
        assert edit_event.field_name == "quantity"
        assert edit_event.new_value == "100.0"
        assert edit_event.notes == "Confirmed quantity with customer"


class TestAPIEndpoints:
    """Verifies FastAPI REST endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_health_endpoint(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["catalog_size"] >= 20

    def test_create_rfq_from_pasted_text(self, client):
        text = "10 pcs Schneider Electric LC1D09BD\n5 pcs Siemens 6ES7214-1AG40-0XB0"
        resp = client.post(
            "/api/rfqs",
            data={"pasted_text": text, "title": "API Test RFQ", "actor": "Test User"},
        )
        assert resp.status_code == 200
        case_data = resp.json()
        case_id = case_data["case_id"]
        coverage = case_data["source_coverage"]
        assert len(coverage) == 1
        assert coverage[0]["unit_id"] == "document"
        assert coverage[0]["nonempty_regions"] == 2
        assert coverage[0]["structured_regions"] == 2
        assert coverage[0]["locator"]["text_snippet"] is None
        assert len(coverage[0]["content_sha256"]) == 64
        assert client.get(f"/api/rfqs/{case_id}").json()["source_coverage"] == coverage

        # Fetch lines
        lines_resp = client.get(f"/api/rfqs/{case_id}/lines")
        assert lines_resp.status_code == 200
        lines = lines_resp.json()
        assert len(lines) == 2
        assert lines[0]["requested_mpn"] == "LC1D09BD"
        assert lines[0]["selected_catalog_sku"] == "SKU-SCH-001"

        # Update and approve line
        line1_id = lines[0]["line_id"]
        patch_resp = client.patch(
            f"/api/rfqs/{case_id}/lines/{line1_id}",
            json={"review_decision": "APPROVED", "expected_version": lines[0]["version"], "actor": "Test Reviewer"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["review_decision"] == "APPROVED"

        # Check audit trail
        audit_resp = client.get(f"/api/rfqs/{case_id}/audit")
        assert audit_resp.status_code == 200
        events = audit_resp.json()
        assert any(e["action"] == "LINE_APPROVED" for e in events)
