"""Fail-closed export regression tests for invalid quantities and critical warnings."""

import math

import pytest

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.exports.generator import ExportGenerator, ExportValidationError
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.quotation.line_rules import blocking_line_issues
from rfq_assistant.schemas.enums import CaseStatus, ReviewDecision
from rfq_assistant.schemas.models import CatalogItem, ExportRequest, RFQLineItemUpdate


@pytest.fixture
def services(tmp_path):
    catalog = CatalogRepository()
    catalog.add_item(
        CatalogItem(
            internal_sku="SKU-SYN-1",
            manufacturer="Schneider Electric",
            manufacturer_part_number="LC1D09BD",
            description="Synthetic contactor",
            list_price=45.0,
        )
    )
    catalog.add_item(
        CatalogItem(
            internal_sku="SKU-SYN-2",
            manufacturer="Siemens",
            manufacturer_part_number="6ES7214-1AG40-0XB0",
            description="Synthetic PLC",
            list_price=280.0,
        )
    )
    manager = CaseManager(catalog=catalog, storage=DocumentStorage(tmp_path / "uploads"))
    exporter = ExportGenerator(catalog=catalog, base_export_dir=tmp_path / "exports")
    return manager, exporter, catalog


@pytest.mark.parametrize("raw_quantity", ["0", "-5"])
def test_nonpositive_csv_quantity_never_becomes_export_ready(services, raw_quantity):
    manager, exporter, _ = services
    csv_content = (
        "MPN,Manufacturer,Qty,Description\n"
        f"LC1D09BD,Schneider Electric,{raw_quantity},Synthetic contactor\n"
    ).encode("utf-8")
    case = manager.create_case_from_upload(filename="rfq.csv", content=csv_content)
    line = manager.get_lines(case.case_id)[0]
    assert line.quantity == float(raw_quantity)
    manager.update_line(
        case.case_id,
        line.line_id,
        RFQLineItemUpdate(review_decision=ReviewDecision.APPROVED),
    )
    assert manager.get_case(case.case_id).status == CaseStatus.NEEDS_REVIEW
    assert manager.get_case(case.case_id).unresolved_count == 1

    with pytest.raises(ExportValidationError, match="quantity must be positive and finite"):
        exporter.generate_export(
            case, manager.get_lines(case.case_id),
            ExportRequest(case_id=case.case_id, format="xlsx", allow_partial=False),
        )


def test_nonfinite_quantity_cannot_pass_shared_gate(services):
    manager, _, catalog = services
    case = manager.create_case_from_text("10 pcs Schneider Electric LC1D09BD")
    line = manager.get_lines(case.case_id)[0]
    line.quantity = math.nan  # Simulates malicious/incorrect parser output.
    line.review_decision = ReviewDecision.APPROVED
    assert "quantity must be positive and finite" in blocking_line_issues(line, catalog)


def test_unknown_manual_sku_cannot_be_export_ready(services):
    manager, exporter, _ = services
    case = manager.create_case_from_text("10 pcs Schneider Electric LC1D09BD")
    line = manager.get_lines(case.case_id)[0]
    manager.update_line(
        case.case_id,
        line.line_id,
        RFQLineItemUpdate(selected_catalog_sku="NONEXISTENT-SKU", review_decision=ReviewDecision.APPROVED),
    )
    assert manager.get_case(case.case_id).status == CaseStatus.NEEDS_REVIEW
    with pytest.raises(ExportValidationError, match="selected catalog SKU is missing or unknown"):
        exporter.generate_export(
            case, manager.get_lines(case.case_id),
            ExportRequest(case_id=case.case_id, allow_partial=False),
        )


def test_explicitly_approved_cross_oem_override_still_blocks_full_export(services):
    manager, exporter, _ = services
    case = manager.create_case_from_text("10 pcs Schneider Electric LC1D09BD")
    line = manager.get_lines(case.case_id)[0]
    manager.update_line(
        case.case_id,
        line.line_id,
        RFQLineItemUpdate(selected_catalog_sku="SKU-SYN-2", review_decision=ReviewDecision.APPROVED),
    )
    assert line.review_decision == ReviewDecision.APPROVED
    assert any(w.severity == "error" and w.code == "CONTRADICTION" for w in line.extraction_warnings)
    assert manager.get_case(case.case_id).status == CaseStatus.NEEDS_REVIEW

    with pytest.raises(ExportValidationError, match="CONTRADICTION"):
        exporter.generate_export(
            case, manager.get_lines(case.case_id),
            ExportRequest(case_id=case.case_id, allow_partial=False),
        )

    partial = exporter.generate_export(
        case, manager.get_lines(case.case_id),
        ExportRequest(case_id=case.case_id, allow_partial=True),
    )
    assert partial.is_draft
    assert partial.unresolved_lines_omitted == 1


def test_valid_reviewed_exact_match_can_still_export(services):
    manager, exporter, _ = services
    case = manager.create_case_from_text("10 pcs Schneider Electric LC1D09BD")
    line = manager.get_lines(case.case_id)[0]
    manager.update_line(
        case.case_id,
        line.line_id,
        RFQLineItemUpdate(review_decision=ReviewDecision.APPROVED),
    )
    assert manager.get_case(case.case_id).status == CaseStatus.READY_TO_EXPORT
    manifest = exporter.generate_export(
        case, manager.get_lines(case.case_id),
        ExportRequest(case_id=case.case_id, allow_partial=False),
    )
    assert manifest.approved_lines == 1
    assert manifest.unresolved_lines_omitted == 0
