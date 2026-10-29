"""Regression tests: never lose a headerless BOM row or turn empty parsing into success."""

import pytest

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion import DocumentParserError, DocumentStorage
from rfq_assistant.ingestion.parsers.spreadsheet_parser import SpreadsheetParser
from rfq_assistant.matching.catalog import CatalogRepository


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


@pytest.mark.parametrize("filename,content", [
    ("empty_lines.csv", b"MPN,Qty,Description\n"),
    ("no_lines.txt", b"Hello team. Thank you for your time.\n"),
])
def test_no_lines_rejected_without_orphan_case_files(tmp_path, filename, content):
    storage = DocumentStorage(base_dir=tmp_path / "files")
    manager = CaseManager(catalog=CatalogRepository(), storage=storage)
    with pytest.raises(DocumentParserError, match="No RFQ line items"):
        manager.create_case_from_upload(filename=filename, content=content)

    assert manager.list_cases() == []
    assert not any(path.is_file() for path in (tmp_path / "files").rglob("*"))


def test_csv_parser_surfaces_explicit_error_for_no_items():
    result = SpreadsheetParser().parse(b"MPN,Qty,Description\n", "headers_only.csv")
    assert result.lines == []
    assert any(w.code == "NO_LINES_EXTRACTED" and w.severity == "error" for w in result.warnings)
