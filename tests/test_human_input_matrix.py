"""Ten synthetic human-input shapes must yield grounded rows or visible exceptions."""

from pathlib import Path

import pytest

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.parsers.base import DocumentParserError
from rfq_assistant.ingestion.parsers.pdf_parser import PDFParser
from rfq_assistant.ingestion.parsers.spreadsheet_parser import SpreadsheetParser
from rfq_assistant.ingestion.parsers.text_parser import TextParser
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository

FIXTURES = Path(__file__).parent / "end_to_end_audit" / "fixtures"

HUMAN_TEXT_CASES = [
    (
        "H01-typo-email",
        "hey can u quote 4 pcs of Phoenix Contact 2900364 power supply? need it next month",
    ),
    (
        "H02-chat-shorthand-with-implicit-item",
        "pls quote 2x Siemens 6ES7134-6GD01-0BA1 + 5 of the same relay as last time",
    ),
    (
        "H03-forwarded-correction-thread",
        "From: buyer@example.test\nSubject: correction\n"
        "> Siemens 6ES7134-6GD01-0BA1 qty 8 ea\n"
        "Correction: Siemens 6ES7134-6GD01-0BA1 qty 3 ea",
    ),
    (
        "H04-dictation-with-self-correction",
        "Voice note transcript: uh Siemens 6ES7134-6GD01-0BA1 quantity 4, no sorry fourteen, for next week",
    ),
    (
        "H05-hinglish-message",
        "bhai please quote 3 pcs Siemens 6ES7134-6GD01-0BA1 jaldi, delivery baad mein confirm",
    ),
    (
        "H06-generic-rfq-form-without-mpn",
        "[COMPANY NAME]\nSubject: Request for Quotation for Product Service Name\n"
        "Delivery deadline, taxes, warranty, and address only",
    ),
]


@pytest.mark.parametrize(("case_id", "text"), HUMAN_TEXT_CASES, ids=[case[0] for case in HUMAN_TEXT_CASES])
def test_conversational_inputs_keep_source_regions_visible(case_id, text):
    result = TextParser().parse(text.encode("utf-8"), f"{case_id}.txt")

    assert result.source_coverage
    assert sum(unit.nonempty_regions for unit in result.source_coverage) == sum(
        unit.structured_regions + unit.review_regions + unit.filtered_regions
        for unit in result.source_coverage
    )

    if case_id == "H01-typo-email":
        assert len(result.lines) == 1
        assert result.lines[0].requested_mpn == "2900364"
        assert result.lines[0].quantity == 4
    elif case_id == "H02-chat-shorthand-with-implicit-item":
        assert not result.lines
        assert len(result.candidate_segments) == 1
        assert "same relay as last time" in result.candidate_segments[0].text
    elif case_id == "H03-forwarded-correction-thread":
        assert [line.quantity for line in result.lines] == [8, 3]
        assert all(
            any(warning.code == "REPEATED_PART_QUANTITY_REQUIRES_REVIEW" for warning in line.extraction_warnings)
            for line in result.lines
        )
    elif case_id == "H04-dictation-with-self-correction":
        assert len(result.lines) == 1
        assert result.lines[0].quantity is None
        assert any(warning.code == "MISSING_QUANTITY" for warning in result.lines[0].extraction_warnings)
    elif case_id == "H05-hinglish-message":
        assert len(result.lines) == 1
        assert result.lines[0].requested_mpn == "6ES7134-6GD01-0BA1"
        assert result.lines[0].quantity == 3
    elif case_id == "H06-generic-rfq-form-without-mpn":
        assert not result.lines
        assert result.candidate_segments or result.warnings


def test_alternate_header_csv_is_source_linked():
    result = SpreadsheetParser().parse(
        (FIXTURES / "layout_alt_headers.csv").read_bytes(), "layout_alt_headers.csv"
    )
    assert len(result.lines) == 3
    assert all(line.source_locator.row_number is not None for line in result.lines)
    assert result.source_coverage


def test_workbook_with_title_before_headers_is_source_linked():
    result = SpreadsheetParser().parse(
        (FIXTURES / "xlsx_title_then_header.xlsx").read_bytes(),
        "xlsx_title_then_header.xlsx",
    )
    assert len(result.lines) == 2
    assert all(line.source_locator.sheet_name for line in result.lines)
    assert result.source_coverage


def test_wrapped_native_pdf_keeps_multiple_lines_and_page_locators():
    result = PDFParser(allow_ocr=False).parse(
        (FIXTURES / "wrapped_description_pdf.pdf").read_bytes(),
        "wrapped_description_pdf.pdf",
    )
    assert len(result.lines) >= 2
    assert all(line.source_locator.page_number for line in result.lines)
    assert result.source_coverage


def test_image_only_pdf_fails_explicitly_when_ocr_is_unavailable():
    with pytest.raises(DocumentParserError, match="Scanned or image-only PDF"):
        PDFParser(allow_ocr=False).parse(
            (FIXTURES / "scanned_image_pdf.pdf").read_bytes(),
            "scanned_image_pdf.pdf",
        )


def test_ten_human_input_shapes_complete_case_intake_without_silent_loss(tmp_path, monkeypatch):
    """Exercise the case boundary for messy text and four document-layout classes."""
    import rfq_assistant.cases.manager as manager_module

    original_get_parser = manager_module.get_parser

    def parser_without_ocr(source_type):
        if source_type.value.startswith("PDF"):
            return PDFParser(allow_ocr=False)
        return original_get_parser(source_type)

    monkeypatch.setattr(manager_module, "get_parser", parser_without_ocr)
    manager = CaseManager(
        catalog=CatalogRepository(),
        storage=DocumentStorage(tmp_path / "sources"),
    )

    scenarios = [
        ("H01-typo-email", "text", HUMAN_TEXT_CASES[0][1]),
        ("H02-chat-shorthand", "text", HUMAN_TEXT_CASES[1][1]),
        ("H03-forwarded-correction", "text", HUMAN_TEXT_CASES[2][1]),
        ("H04-dictation-correction", "text", HUMAN_TEXT_CASES[3][1]),
        ("H05-hinglish", "text", HUMAN_TEXT_CASES[4][1]),
        ("H06-no-mpn-template", "text", HUMAN_TEXT_CASES[5][1]),
        ("H07-title-row-workbook", "xlsx", FIXTURES / "xlsx_title_then_header.xlsx"),
        ("H08-headerless-csv", "csv", FIXTURES / "headerless_csv.csv"),
        ("H09-wrapped-native-pdf", "pdf", FIXTURES / "wrapped_description_pdf.pdf"),
        ("H10-scanned-pdf-no-ocr", "pdf", FIXTURES / "scanned_image_pdf.pdf"),
    ]

    for case_id, kind, value in scenarios:
        if kind == "text":
            case = manager.create_case_from_text(value, title=f"Synthetic {case_id}")
        else:
            content = Path(value).read_bytes()
            case = manager.create_case_from_upload(
                filename=f"{case_id}.{kind}",
                content=content,
                title=f"Synthetic {case_id}",
            )

        assert case.case_id
        assert case.source_coverage or case.status.value == "FAILED", case_id
        lines = manager.get_lines(case.case_id)
        original = manager.storage.uploads_dir / case.case_id / case.source_file.file_name
        assert original.is_file(), case_id
        assert lines or case.document_warnings or case.status.value == "FAILED", case_id

        if case_id == "H10-scanned-pdf-no-ocr":
            assert case.status.value == "FAILED"
            assert case.document_warnings or case.source_coverage
        else:
            assert case.status.value != "FAILED", case_id
