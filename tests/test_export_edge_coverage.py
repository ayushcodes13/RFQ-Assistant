"""Exercise defensive export-list and clarification-draft branches."""

import json

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.exports.email_draft import generate_unsent_email_draft
from rfq_assistant.exports.generator import ExportGenerator
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.schemas.enums import MatchStatus, ReviewDecision, SourceType
from rfq_assistant.schemas.models import (
    CatalogItem,
    ExportRequest,
    MatchCandidate,
    RFQCase,
    RFQLineItem,
    SourceLocator,
)


def test_export_list_skips_invalid_records_and_reports_missing_file(tmp_path):
    catalog = CatalogRepository()
    export_root = tmp_path / "exports"
    generator = ExportGenerator(catalog, base_export_dir=export_root)
    export_root.rmdir()
    assert generator.list_exports("RFQ-SYN-1") == []

    export_root.mkdir()
    (export_root / "not-an-export").mkdir()
    (export_root / "EXP-11111111").mkdir()
    (export_root / "EXP-22222222").mkdir()
    (export_root / "EXP-22222222" / "manifest.json").write_text("{")
    broken_manifest = export_root / "EXP-33333333"
    broken_manifest.mkdir()
    (broken_manifest / "manifest.json").write_text(
        json.dumps(
            {
                "case_id": "RFQ-SYN-1",
                "file_name": "../outside.exe",
                "generated_at": "not-a-date",
            }
        )
    )

    records = generator.list_exports("RFQ-SYN-1")
    assert len(records) == 1
    assert records[0].format == "xlsx"
    assert not records[0].file_available
    assert records[0].problem == "Generated document file is missing."


def test_export_uses_xlsx_fallback_and_includes_page_locator(tmp_path):
    catalog = CatalogRepository()
    manager = CaseManager(
        catalog=catalog, storage=DocumentStorage(tmp_path / "uploads")
    )
    case = manager.create_case_from_text("10 pcs Schneider Electric LC1D09BD")
    line = manager.get_lines(case.case_id)[0]
    line.source_locator.page_number = 2
    generator = ExportGenerator(catalog, base_export_dir=tmp_path / "exports")

    manifest = generator.generate_export(
        case,
        [line],
        ExportRequest(
            case_id=case.case_id,
            allow_partial=True,
            format="ods",
        ),
    )

    assert manifest.format == "xlsx"


def _line(*, match=MatchStatus.COLLISION, candidates=None, unit="EA", notes=None):
    return RFQLineItem(
        line_id="SYN-LINE-1",
        case_id="RFQ-SYN-1",
        line_number=1,
        raw_text="10 pcs synthetic relay",
        source_locator=SourceLocator(file_name="synthetic.txt"),
        requested_mpn="RELAY-100",
        quantity=0,
        unit=unit,
        match_status=match,
        review_decision=ReviewDecision.NEEDS_CLARIFICATION,
        reviewer_notes=notes,
        candidates=candidates or [],
    )


def _candidate(manufacturer):
    return MatchCandidate(
        catalog_item=CatalogItem(
            internal_sku=f"SKU-{manufacturer[:3]}",
            manufacturer=manufacturer,
            manufacturer_part_number="RELAY-100",
            description="Synthetic relay",
        ),
        match_type=MatchStatus.EXACT_MATCH,
        explanation="synthetic fixture",
        confidence_note="review required",
    )


def test_email_clarification_covers_collision_unit_and_reviewer_note_paths():
    case = RFQCase(
        case_id="RFQ-SYN-1", title="Synthetic", source_type=SourceType.EMAIL_TEXT
    )
    lines = [
        _line(
            candidates=[_candidate("Acme"), _candidate("Apex")],
            unit=None,
            notes="Check suffix",
        ),
        _line(candidates=[_candidate("Acme")]),
    ]

    draft = generate_unsent_email_draft(case, lines)

    assert "appears under different manufacturers" in draft
    assert "confirm the manufacturer" in draft
    assert "requested unit or packaging" in draft
    assert "Check suffix" in draft
    assert "valid positive quantity" in draft
