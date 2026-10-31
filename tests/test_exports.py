"""Unit and API tests for quotation worksheet export, draft banners, and email generation."""

from pathlib import Path
import openpyxl
import pytest
from fastapi.testclient import TestClient

from rfq_assistant.api.app import app, catalog_repo, case_manager, export_generator
from rfq_assistant.exports import ExportValidationError, generate_unsent_email_draft
from rfq_assistant.schemas.enums import ReviewDecision
from rfq_assistant.schemas.models import ExportRequest, RFQLineItemUpdate

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT / "fixtures" / "rfq_samples"


class TestExportEngine:
    """Verifies deterministic export generation, draft warnings, and safety blockers."""

    @pytest.fixture
    def test_case_and_lines(self):
        # Create case from clean 20-line BOM
        xlsx_path = SAMPLES_DIR / "industrial_control_bom_20lines.xlsx"
        case = case_manager.create_case_from_upload(
            filename="industrial_control_bom_20lines.xlsx",
            content=xlsx_path.read_bytes(),
            customer_label="Acme Industrial",
            actor="Reviewer Alice",
        )
        lines = case_manager.get_lines(case.case_id)
        return case, lines

    def test_export_blocked_when_unresolved_lines_exist(self, test_case_and_lines):
        case, lines = test_case_and_lines
        req = ExportRequest(case_id=case.case_id, allow_partial=False)

        # Unresolved lines (missing quantity on line 18, pending approvals) must block final export
        with pytest.raises(ExportValidationError, match="Export blocked"):
            export_generator.generate_export(case, lines, req)

    def test_partial_export_allowed_with_explicit_flag(self, test_case_and_lines, tmp_path):
        case, lines = test_case_and_lines
        generator = export_generator
        req = ExportRequest(case_id=case.case_id, allow_partial=True, format="xlsx")

        manifest = generator.generate_export(case, lines, req)
        assert manifest.is_draft is True
        assert manifest.total_lines == 20
        assert manifest.unresolved_lines_omitted > 0

        # Verify generated XLSX contents
        file_path = Path("storage/exports") / manifest.export_id / manifest.file_name
        assert file_path.exists()
        wb = openpyxl.load_workbook(file_path)
        ws = wb.active
        assert "Quote Preparation" in wb.sheetnames
        # Check draft banner in row 1
        assert "DRAFT QUOTATION WORKSHEET" in str(ws["A1"].value)
        # Check metadata
        assert str(ws["B2"].value) == case.case_id

    def test_export_csv_format(self, test_case_and_lines):
        case, lines = test_case_and_lines
        req = ExportRequest(case_id=case.case_id, allow_partial=True, format="csv")

        manifest = export_generator.generate_export(case, lines, req)
        assert manifest.format == "csv"
        file_path = Path("storage/exports") / manifest.export_id / manifest.file_name
        assert file_path.exists()
        csv_text = file_path.read_text(encoding="utf-8")
        assert "DRAFT QUOTATION WORKSHEET" in csv_text
        assert "line_number,review_status,requested_oem" in csv_text

    def test_manual_override_with_oem_contradiction_remains_blocked(self, test_case_and_lines):
        case, lines = test_case_and_lines

        # Fix line 18 quantity, assign manual SKU for unmatched line 19, and approve all 20 lines
        for line in lines:
            sku_override = "SKU-SCH-005" if line.line_number == 19 else None
            case_manager.update_line(
                case.case_id,
                line.line_id,
                RFQLineItemUpdate(
                    quantity=line.quantity or 10.0,
                    selected_catalog_sku=sku_override,
                    review_decision=ReviewDecision.APPROVED,
                    actor="Reviewer Alice",
                ),
            )

        updated_lines = case_manager.get_lines(case.case_id)
        req = ExportRequest(case_id=case.case_id, allow_partial=False, format="xlsx")
        with pytest.raises(ExportValidationError, match="CONTRADICTION"):
            export_generator.generate_export(case, updated_lines, req)

        partial = ExportRequest(case_id=case.case_id, allow_partial=True, format="xlsx")
        manifest = export_generator.generate_export(case, updated_lines, partial)
        assert manifest.approved_lines == 20
        assert manifest.unresolved_lines_omitted >= 1
        assert manifest.is_draft

    def test_unsent_email_draft_clarifications(self, test_case_and_lines):
        case, lines = test_case_and_lines
        email_text = generate_unsent_email_draft(case, lines)

        # Invariant checks
        assert "*** UNSENT DRAFT REPLY" in email_text
        assert "NO AUTOMATIC OUTBOUND DISPATCH" in email_text
        # Clarifications must address missing quantity
        assert "Quantity was missing from the request" in email_text


class TestExportAPIEndpoints:
    """Verifies REST endpoints for export generation and download."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_export_and_download_flow(self, client):
        # Create case
        text = "10 pcs Schneider Electric LC1D09BD"
        create_resp = client.post("/api/rfqs", data={"pasted_text": text, "title": "Export Flow Test"})
        assert create_resp.status_code == 200
        case_id = create_resp.json()["case_id"]

        lines = client.get(f"/api/rfqs/{case_id}/lines").json()
        line_id = lines[0]["line_id"]

        # Approve line
        client.patch(f"/api/rfqs/{case_id}/lines/{line_id}", json={"review_decision": "APPROVED", "expected_version": lines[0]["version"]})

        # Export worksheet
        export_resp = client.post(
            f"/api/rfqs/{case_id}/exports",
            json={"case_id": case_id, "allow_partial": False, "format": "xlsx", "actor": "Test Reviewer"},
        )
        assert export_resp.status_code == 200
        manifest = export_resp.json()
        export_id = manifest["export_id"]

        # Download file
        download_resp = client.get(f"/api/rfqs/{case_id}/exports/{export_id}")
        assert download_resp.status_code == 200
        assert len(download_resp.content) > 0
        assert "spreadsheetml" in download_resp.headers["content-type"]

        # Email draft endpoint
        draft_resp = client.get(f"/api/rfqs/{case_id}/email-draft")
        assert draft_resp.status_code == 200
        assert "UNSENT DRAFT" in draft_resp.json()["draft"]
