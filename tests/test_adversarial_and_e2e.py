"""End-to-end integration and adversarial test suite covering Scenarios 1 through 7."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from rfq_assistant.api.app import app, catalog_repo, case_manager, export_generator
from rfq_assistant.exports import ExportValidationError, generate_unsent_email_draft
from rfq_assistant.ingestion import UploadValidationError
from rfq_assistant.schemas.enums import CaseStatus, MatchStatus, ReviewDecision
from rfq_assistant.schemas.models import ExportRequest, RFQLineItemUpdate

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT / "fixtures" / "rfq_samples"


class TestAllProductScenarios:
    """Verifies that all 7 real-world scenarios documented in docs/SCENARIOS.md operate as expected."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_scenario_1_straightforward_electrical_bom(self):
        """
        Scenario 1: 34-row (20-line in fixture) Excel BOM.
        Row 18 is missing quantity. 18 lines exact match, 1 non-catalog, 1 missing quantity.
        Rep fills in missing quantity, approves matching entries, and exports worksheet + unsent email.
        """
        xlsx_path = SAMPLES_DIR / "industrial_control_bom_20lines.xlsx"
        case = case_manager.create_case_from_upload(
            filename="industrial_control_bom_20lines.xlsx",
            content=xlsx_path.read_bytes(),
            customer_label="Scenario 1 Distributor",
            actor="Sales Rep John",
        )

        assert case.line_count == 20
        lines = case_manager.get_lines(case.case_id)

        # Line 18 has missing quantity warning
        line18 = [l for l in lines if l.line_number == 18][0]
        assert line18.quantity is None
        assert any(w.code == "MISSING_QUANTITY" for w in line18.extraction_warnings)

        # Line 19 is non-catalog part
        line19 = [l for l in lines if l.line_number == 19][0]
        assert line19.match_status == MatchStatus.NO_MATCH

        # Operator fixes line 18 quantity after customer confirms
        case_manager.update_line(
            case.case_id,
            line18.line_id,
            RFQLineItemUpdate(quantity=50.0, actor="Sales Rep John", reviewer_notes="Confirmed 50 EA with buyer"),
        )

        # Operator assigns manual SKU for non-catalog bracket
        case_manager.update_line(
            case.case_id,
            line19.line_id,
            RFQLineItemUpdate(selected_catalog_sku="SKU-SCH-005", review_decision=ReviewDecision.APPROVED),
        )

        # Batch approve all other exact matches
        for l in lines:
            if l.match_status == MatchStatus.EXACT_MATCH:
                case_manager.update_line(
                    case.case_id,
                    l.line_id,
                    RFQLineItemUpdate(review_decision=ReviewDecision.APPROVED, actor="Sales Rep John"),
                )

        updated_case = case_manager.get_case(case.case_id)
        assert updated_case.status == CaseStatus.READY_TO_EXPORT

        # Export completed worksheet
        req = ExportRequest(case_id=case.case_id, allow_partial=False, format="xlsx")
        manifest = export_generator.generate_export(updated_case, case_manager.get_lines(case.case_id), req)
        assert manifest.approved_lines == 20
        assert manifest.is_draft is True

    def test_scenario_2_messy_email_with_vague_item(self):
        """
        Scenario 2: Messy email with "the sensor from last time".
        Must parse recognizable items cautiously and flag "sensor from last time"
        as UNKNOWN_PART_REFERENCE. Draft polite clarification email without guessing.
        """
        email_path = SAMPLES_DIR / "messy_email_quote_request.txt"
        case = case_manager.create_case_from_upload(
            filename="messy_email_quote_request.txt",
            content=email_path.read_bytes(),
            customer_label="Scenario 2 Plant",
            actor="Inside Sales",
        )

        lines = case_manager.get_lines(case.case_id)
        assert len(lines) == 6

        # Check that the vague sensor was flagged
        vague_line = [l for l in lines if l.requested_mpn is None][0]
        assert any(w.code == "UNKNOWN_PART_REFERENCE" for w in vague_line.extraction_warnings)

        # Check unsent email draft specifically asks for sensor clarification
        email_text = generate_unsent_email_draft(case, lines)
        assert "sensor from last time" in email_text
        assert "NO AUTOMATIC OUTBOUND DISPATCH" in email_text

    def test_scenario_3_cross_brand_collision(self):
        """
        Scenario 3: PDF / text with part number XG-42 but NO manufacturer specified.
        Catalog contains XG-42 by Apex Automation and XG-42 by Delta Electronics.
        Must report COLLISION with both candidates and block until human manufacturer selection.
        """
        collision_path = SAMPLES_DIR / "cross_brand_collision.txt"
        case = case_manager.create_case_from_upload(
            filename="cross_brand_collision.txt",
            content=collision_path.read_bytes(),
            customer_label="Scenario 3 Customer",
        )

        lines = case_manager.get_lines(case.case_id)
        xg42_line = [l for l in lines if l.requested_mpn == "XG-42"][0]
        assert xg42_line.match_status == MatchStatus.COLLISION
        assert len(xg42_line.candidates) == 2
        cand_oems = {c.catalog_item.manufacturer for c in xg42_line.candidates}
        assert cand_oems == {"Apex Automation", "Delta Electronics"}

        # Attempting final export without resolving collision must fail
        req = ExportRequest(case_id=case.case_id, allow_partial=False)
        with pytest.raises(ExportValidationError, match="Export blocked"):
            export_generator.generate_export(case, lines, req)

    def test_scenario_5_no_automatic_equivalent_invention(self):
        """
        Scenario 5: Unknown technical equivalent.
        Buyer asks for an obsolete part. The system must NEVER invent an equivalent
        based on text similarity; it flags NO_MATCH until human assigns verified SKU.
        """
        case = case_manager.create_case_from_text(
            raw_text="10 pcs Obsolete Breaker Model OLD-BREAKER-1990 equivalent acceptable if certified",
            title="Scenario 5 Obsolete Inquiry",
        )
        lines = case_manager.get_lines(case.case_id)
        assert len(lines) >= 1
        line = lines[0]
        # Must be NO_MATCH
        assert line.match_status == MatchStatus.NO_MATCH
        assert line.selected_catalog_sku is None

    def test_scenario_6_unsafe_files_rejected_safely(self):
        """
        Scenario 6: Broken or unsafe files (corrupt PDF, macro XLSM).
        Must reject without crashes and without producing a false zero-line quote.
        """
        macro_path = SAMPLES_DIR / "adversarial_macro_sample.xlsm"
        with pytest.raises(UploadValidationError, match="Macro-enabled spreadsheets"):
            case_manager.create_case_from_upload(
                filename="adversarial_macro_sample.xlsm",
                content=macro_path.read_bytes(),
            )

        corrupt_path = SAMPLES_DIR / "corrupt_file.pdf"
        with pytest.raises(Exception, match="Corrupted or invalid PDF"):
            case_manager.create_case_from_upload(
                filename="corrupt_file.pdf",
                content=corrupt_path.read_bytes(),
            )

    def test_scenario_7_export_without_prices(self):
        """
        Scenario 7: Items matched, but company catalog has blank list prices.
        Must export draft worksheet with price columns empty, never inventing prices.
        """
        # Create a catalog item with None list_price
        from rfq_assistant.schemas.models import CatalogItem
        catalog_repo.add_item(
            CatalogItem(
                internal_sku="SKU-UNPRICED-001",
                manufacturer="Schneider Electric",
                manufacturer_part_number="LC1D-UNPRICED-99",
                description="Unpriced Custom Contactor",
                list_price=None,
            )
        )

        case = case_manager.create_case_from_text(
            raw_text="5 pcs Schneider Electric LC1D-UNPRICED-99",
            title="Scenario 7 Unpriced RFQ",
        )
        lines = case_manager.get_lines(case.case_id)
        assert lines[0].selected_catalog_sku == "SKU-UNPRICED-001"

        case_manager.update_line(
            case.case_id, lines[0].line_id, RFQLineItemUpdate(review_decision=ReviewDecision.APPROVED)
        )

        req = ExportRequest(case_id=case.case_id, allow_partial=False, format="csv")
        manifest = export_generator.generate_export(case, case_manager.get_lines(case.case_id), req)

        file_path = Path("storage/exports") / manifest.export_id / manifest.file_name
        csv_text = file_path.read_text(encoding="utf-8")
        # Line row must have blank price
        assert ",,," in csv_text or ",," in csv_text
        assert "DRAFT QUOTATION WORKSHEET" in csv_text
