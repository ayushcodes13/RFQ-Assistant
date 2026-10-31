"""Regression tests: never lose a headerless BOM row or turn empty parsing into success."""

import pytest
from io import BytesIO
from openpyxl import Workbook

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.parsers.base import DocumentParserError
from rfq_assistant.ingestion import DocumentStorage
from rfq_assistant.ingestion.parsers.spreadsheet_parser import SpreadsheetParser
from rfq_assistant.ingestion.parsers.text_parser import TextParser
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.persistence import SQLiteStateStore


def test_headerless_csv_retains_first_row_and_original_row_numbers():
    content = (
        b"LC1D09BD,10,Contactor\n"
        b"6ES7214-1AG40-0XB0,5,PLC\n"
    )
    parsed = SpreadsheetParser().parse(content, "headerless.csv")
    assert len(parsed.lines) == 2
    assert [line.requested_mpn for line in parsed.lines] == [
        "LC1D09BD", "6ES7214-1AG40-0XB0",
    ]
    assert [line.source_locator.row_number for line in parsed.lines] == [1, 2]
    assert [line.quantity for line in parsed.lines] == [10, 5]


def test_csv_missing_part_reference_is_reviewable_instead_of_dropped():
    parsed = SpreadsheetParser().parse(
        b"MPN,Qty,Description\n,3,\nLC1D09BD,10,Contactor\n", "incomplete.csv"
    )
    assert len(parsed.lines) == 2
    missing = parsed.lines[0]
    assert missing.source_locator.row_number == 2
    assert missing.quantity == 3
    assert missing.requested_mpn is None
    assert any(w.code == "MISSING_PART_REFERENCE" for w in missing.extraction_warnings)


def test_header_only_csv_is_rejected_before_case_or_file_creation(tmp_path):
    storage = DocumentStorage(base_dir=tmp_path / "files")
    manager = CaseManager(catalog=CatalogRepository(), storage=storage)
    with pytest.raises(DocumentParserError, match="headers but no RFQ line items"):
        manager.create_case_from_upload(filename="empty_lines.csv", content=b"MPN,Qty,Description\n")
    assert manager.list_cases() == []
    assert not list(storage.uploads_dir.glob("**/*"))


def test_header_only_xlsx_is_rejected_before_case_or_file_creation(tmp_path):
    workbook = Workbook()
    workbook.active.append(["MPN", "Manufacturer", "Quantity", "Description"])
    output = BytesIO()
    workbook.save(output)
    storage = DocumentStorage(base_dir=tmp_path / "files")
    manager = CaseManager(catalog=CatalogRepository(), storage=storage)
    with pytest.raises(DocumentParserError, match="headers but no RFQ line items"):
        manager.create_case_from_upload(filename="empty_lines.xlsx", content=output.getvalue())
    assert manager.list_cases() == []
    assert not list(storage.uploads_dir.glob("**/*"))


@pytest.mark.parametrize("raw_text", ["   \n\t", "\n".join(f"region {i}" for i in range(600))])
def test_unusable_or_over_limit_text_is_rejected_before_case_or_file_creation(tmp_path, raw_text):
    storage = DocumentStorage(base_dir=tmp_path / "files")
    manager = CaseManager(catalog=CatalogRepository(), storage=storage)
    with pytest.raises(DocumentParserError):
        manager.create_case_from_text(raw_text)
    assert manager.list_cases() == []
    assert not list(storage.uploads_dir.glob("**/*"))


def test_nonempty_unclassifiable_text_keeps_source_for_manual_review(tmp_path):
    storage = DocumentStorage(base_dir=tmp_path / "files")
    manager = CaseManager(catalog=CatalogRepository(), storage=storage)
    content = b"Hello team. Thank you for your time.\n"
    case = manager.create_case_from_upload(filename="no_lines.txt", content=content)

    assert case.status.value == "FAILED"
    assert case.processing_stage.value == "FAILED"
    assert any(w.code == "DOCUMENT_EXTRACTION_FAILED" for w in case.document_warnings)
    assert manager.storage.get_file(case.case_id, "no_lines.txt") == content
    assert manager.get_lines(case.case_id) == []


def test_header_only_pasted_text_is_rejected_before_case_or_file_creation(tmp_path):
    storage = DocumentStorage(base_dir=tmp_path / "files")
    manager = CaseManager(catalog=CatalogRepository(), storage=storage)
    with pytest.raises(DocumentParserError, match="only table headers"):
        manager.create_case_from_text("Part Number | Manufacturer | Quantity\n")
    assert manager.list_cases() == []
    assert not list(storage.uploads_dir.glob("**/*"))


def test_async_header_only_paste_is_rejected_before_enqueue_or_file_creation(tmp_path):
    storage = DocumentStorage(base_dir=tmp_path / "files")
    store = SQLiteStateStore(tmp_path / "state.sqlite3")
    manager = CaseManager(catalog=CatalogRepository(state_store=store), storage=storage, state_store=store)
    with pytest.raises(DocumentParserError, match="only table headers"):
        manager.enqueue_case_from_text("Part Number | Manufacturer | Quantity\n")
    assert manager.list_cases() == []
    assert not list(storage.uploads_dir.glob("**/*"))


def test_csv_parser_surfaces_explicit_error_for_no_items():
    result = SpreadsheetParser().parse(b"MPN,Qty,Description\n", "headers_only.csv")
    assert result.lines == []
    assert any(w.code == "NO_LINES_EXTRACTED" and w.severity == "error" for w in result.warnings)


def test_collision_fixture_keeps_only_three_requested_parts():
    from pathlib import Path

    fixture = Path(__file__).parents[1] / "fixtures" / "rfq_samples" / "cross_brand_collision.txt"
    parsed = TextParser().parse(fixture.read_bytes(), fixture.name)
    assert len(parsed.lines) == 3
    assert [line.requested_mpn for line in parsed.lines] == ["XG-42", "ABC-12", "ABC-12-R2"]
    assert not parsed.candidate_segments
