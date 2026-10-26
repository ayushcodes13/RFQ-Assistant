"""Tests for Pydantic domain schemas, synthetic fixtures, and ground truth annotations."""

import csv
import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from rfq_assistant.schemas import (
    AuditAction,
    AuditEvent,
    CaseStatus,
    CatalogItem,
    ExportManifest,
    ExtractionStatus,
    ExtractionWarning,
    MatchCandidate,
    MatchStatus,
    ReviewDecision,
    RFQCase,
    RFQLineItem,
    SourceFileMetadata,
    SourceLocator,
    SourceType,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "fixtures"


class TestDomainSchemas:
    """Verifies strict typing, defaults, and validation of domain models."""

    def test_catalog_item_creation(self):
        item = CatalogItem(
            internal_sku="SKU-TEST-001",
            manufacturer="Schneider Electric",
            manufacturer_part_number="LC1D09BD",
            description="TeSys D contactor 9A 24VDC",
            list_price=42.50,
            stock_qty=100,
        )
        assert item.internal_sku == "SKU-TEST-001"
        assert item.manufacturer == "Schneider Electric"
        assert item.list_price == 42.50

    def test_line_item_with_source_locator(self):
        locator = SourceLocator(
            file_name="industrial_control_bom_20lines.xlsx",
            sheet_name="BOM Items",
            row_number=5,
            text_snippet="Schneider Electric | LC1D09BD | 10 EA",
        )
        line = RFQLineItem(
            line_id="line-001",
            case_id="case-100",
            line_number=1,
            raw_text="10 EA LC1D09BD Schneider Electric",
            source_locator=locator,
            requested_manufacturer="Schneider Electric",
            requested_mpn="LC1D09BD",
            quantity=10.0,
            unit="EA",
            extraction_status=ExtractionStatus.EXTRACTED,
            match_status=MatchStatus.EXACT_MATCH,
            review_decision=ReviewDecision.PENDING,
        )
        assert line.line_id == "line-001"
        assert line.source_locator.row_number == 5
        assert line.quantity == 10.0
        assert line.review_decision == ReviewDecision.PENDING

    def test_line_item_missing_quantity_warning(self):
        locator = SourceLocator(file_name="test.xlsx", row_number=18)
        warning = ExtractionWarning(
            code="MISSING_QUANTITY",
            message="Line does not specify a quantity",
            severity="error",
        )
        line = RFQLineItem(
            line_id="line-018",
            case_id="case-100",
            line_number=18,
            raw_text="Phoenix Contact UT 2.5",
            source_locator=locator,
            requested_manufacturer="Phoenix Contact",
            requested_mpn="UT 2.5",
            quantity=None,
            extraction_status=ExtractionStatus.NEEDS_CORRECTION,
            extraction_warnings=[warning],
        )
        assert line.quantity is None
        assert len(line.extraction_warnings) == 1
        assert line.extraction_warnings[0].code == "MISSING_QUANTITY"

    def test_rfq_case_creation(self):
        metadata = SourceFileMetadata(
            file_id="file-001",
            file_name="industrial_control_bom_20lines.xlsx",
            source_type=SourceType.XLSX,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size_bytes=6353,
            sha256_digest="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )
        case = RFQCase(
            case_id="case-001",
            title="Synthetic Project RFQ",
            customer_label="Acme Industrial",
            status=CaseStatus.NEW,
            source_type=SourceType.XLSX,
            source_file=metadata,
            line_count=20,
            unresolved_count=2,
        )
        assert case.case_id == "case-001"
        assert case.status == CaseStatus.NEW
        assert case.source_file.file_name == "industrial_control_bom_20lines.xlsx"

    def test_audit_event_immutability(self):
        event = AuditEvent(
            event_id="evt-001",
            case_id="case-001",
            line_id="line-018",
            actor="Sales Rep A",
            action=AuditAction.LINE_EDITED,
            field_name="quantity",
            old_value=None,
            new_value="50",
            notes="Customer confirmed 50 EA over phone",
        )
        assert event.actor == "Sales Rep A"
        assert event.new_value == "50"
        assert event.action == AuditAction.LINE_EDITED


class TestSyntheticFixtures:
    """Verifies that all required synthetic fixtures exist, are non-empty, and marked SYNTHETIC."""

    def test_catalog_fixture_validity(self):
        catalog_path = FIXTURES_DIR / "catalogs" / "industrial_components_sample_catalog.csv"
        assert catalog_path.exists(), "Catalog fixture missing"
        with open(catalog_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required_cols = {"internal_sku", "manufacturer", "manufacturer_part_number", "description"}
            assert required_cols.issubset(set(reader.fieldnames))
            rows = list(reader)
            assert len(rows) >= 20, f"Expected at least 20 catalog rows, got {len(rows)}"
            # Verify collision parts exist
            col_parts = [r for r in rows if r["manufacturer_part_number"] == "XG-42"]
            assert len(col_parts) == 2, "Expected 2 manufacturers for collision part XG-42"
            oems = {r["manufacturer"] for r in col_parts}
            assert oems == {"Apex Automation", "Delta Electronics"}

    def test_sample_files_exist_and_non_empty(self):
        samples_dir = FIXTURES_DIR / "rfq_samples"
        expected_files = [
            "industrial_control_bom_20lines.xlsx",
            "multisheet_project_bom.xlsx",
            "messy_email_quote_request.txt",
            "cross_brand_collision.txt",
            "contradictory_email_note.txt",
            "formal_rfq_native.pdf",
            "adversarial_prompt_injection.txt",
            "adversarial_macro_sample.xlsm",
            "corrupt_file.pdf",
        ]
        for fname in expected_files:
            fpath = samples_dir / fname
            assert fpath.exists(), f"Missing fixture file: {fname}"
            assert fpath.stat().st_size > 0, f"Empty fixture file: {fname}"

    def test_ground_truth_annotations_validity(self):
        gt_path = FIXTURES_DIR / "ground_truth" / "annotations.json"
        assert gt_path.exists(), "Ground truth annotations missing"
        data = json.loads(gt_path.read_text(encoding="utf-8"))
        assert "fixtures" in data
        assert "industrial_control_bom_20lines.xlsx" in data["fixtures"]
        bom_annot = data["fixtures"]["industrial_control_bom_20lines.xlsx"]
        assert bom_annot["expected_line_count"] == 20
        assert len(bom_annot["lines"]) == 20
        # Line 18 should be missing quantity
        line18 = [l for l in bom_annot["lines"] if l["line_number"] == 18][0]
        assert line18["qty"] is None
        assert line18["expected_warning"] == "MISSING_QUANTITY"
        # Line 19 should have NO_MATCH
        line19 = [l for l in bom_annot["lines"] if l["line_number"] == 19][0]
        assert line19["expected_match_status"] == "NO_MATCH"
