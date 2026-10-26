"""Unit and integration tests for document validation, storage, and deterministic parsers."""

from pathlib import Path
import pytest

from rfq_assistant.ingestion import (
    DocumentParserError,
    DocumentStorage,
    UploadValidationError,
    compute_sha256,
    get_parser,
    sanitize_filename,
    validate_file_upload,
)
from rfq_assistant.schemas.enums import SourceType

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT / "fixtures" / "rfq_samples"


class TestUploadValidationAndStorage:
    """Verifies security controls, file limits, sanitization, and persistence."""

    def test_sanitize_filename_prevents_traversal(self):
        assert sanitize_filename("../../../etc/passwd") == "passwd"
        assert sanitize_filename("..\\..\\windows\\system32\\cmd.exe") == "cmd.exe"
        assert sanitize_filename(".hidden_file.xlsx") == "upload_.hidden_file.xlsx"

    def test_reject_empty_file(self):
        with pytest.raises(UploadValidationError, match="empty"):
            validate_file_upload("empty.xlsx", b"")

    def test_reject_oversized_file(self):
        oversized = b"A" * (10 * 1024 * 1024 + 1)
        with pytest.raises(UploadValidationError, match="exceeds maximum permitted limit"):
            validate_file_upload("big.csv", oversized)

    def test_reject_macro_spreadsheet(self):
        with pytest.raises(UploadValidationError, match="Macro-enabled spreadsheets"):
            validate_file_upload("bom_with_vba.xlsm", b"DUMMY_CONTENT")

    def test_reject_unsupported_extension(self):
        with pytest.raises(UploadValidationError, match="Unsupported file format"):
            validate_file_upload("script.py", b"print('hello')")

    def test_valid_csv_upload(self):
        content = b"Part Number,Manufacturer,Qty\nLC1D09BD,Schneider Electric,10\n"
        name, src_type, digest = validate_file_upload("parts.csv", content)
        assert name == "parts.csv"
        assert src_type == SourceType.CSV
        assert digest == compute_sha256(content)

    def test_document_storage_save_and_retrieve(self, tmp_path):
        storage = DocumentStorage(base_dir=tmp_path)
        content = b"Sample RFQ Data"
        saved_path = storage.save_file("case-123", "rfq.txt", content)
        assert saved_path.exists()
        retrieved = storage.get_file("case-123", "rfq.txt")
        assert retrieved == content
        storage.delete_case("case-123")
        assert not saved_path.exists()


class TestSpreadsheetParser:
    """Verifies deterministic parsing of XLSX and CSV files with multi-sheet and edge case handling."""

    def test_parse_clean_20line_bom(self):
        file_path = SAMPLES_DIR / "industrial_control_bom_20lines.xlsx"
        content = file_path.read_bytes()
        parser = get_parser(SourceType.XLSX)
        result = parser.parse(content, "industrial_control_bom_20lines.xlsx")

        assert result.total_lines_detected == 20
        assert len(result.lines) == 20

        # Check line 1
        line1 = result.lines[0]
        assert line1.line_number == 1
        assert line1.requested_mpn == "LC1D09BD"
        assert line1.requested_manufacturer == "Schneider Electric"
        assert line1.quantity == 10.0
        assert line1.unit == "EA"
        assert line1.source_locator.sheet_name == "BOM Items"
        assert line1.source_locator.row_number == 5

        # Check line 18: missing quantity must NOT be dropped, but must carry a warning
        line18 = result.lines[17]
        assert line18.line_number == 18
        assert line18.requested_mpn == "UT 2.5"
        assert line18.requested_manufacturer == "Phoenix Contact"
        assert line18.quantity is None
        assert any(w.code == "MISSING_QUANTITY" for w in line18.extraction_warnings)

        # Check line 19: non-catalog item
        line19 = result.lines[18]
        assert line19.requested_mpn == "NONEXISTENT-PART-999"
        assert line19.quantity == 2.0

        # Check line 20: suffix part
        line20 = result.lines[19]
        assert line20.requested_mpn == "ABC-12A"
        assert line20.requested_manufacturer == "Acme Industrial"

    def test_parse_multisheet_project_bom(self):
        file_path = SAMPLES_DIR / "multisheet_project_bom.xlsx"
        content = file_path.read_bytes()
        parser = get_parser(SourceType.XLSX)
        result = parser.parse(content, "multisheet_project_bom.xlsx")

        assert result.total_lines_detected == 5
        sheet_names = {line.source_locator.sheet_name for line in result.lines}
        assert sheet_names == {"Control Panel A", "Field Instrumentation"}

        # Verify items from sheet 1
        panel_a_lines = [l for l in result.lines if l.source_locator.sheet_name == "Control Panel A"]
        assert len(panel_a_lines) == 3

        # Verify items from sheet 2
        field_lines = [l for l in result.lines if l.source_locator.sheet_name == "Field Instrumentation"]
        assert len(field_lines) == 2


class TestPDFParser:
    """Verifies native PDF parsing and safe detection of corrupt/scanned documents."""

    def test_parse_native_pdf(self):
        file_path = SAMPLES_DIR / "formal_rfq_native.pdf"
        content = file_path.read_bytes()
        parser = get_parser(SourceType.PDF_NATIVE)
        result = parser.parse(content, "formal_rfq_native.pdf")

        assert result.total_lines_detected >= 7
        mpns = [l.requested_mpn for l in result.lines]
        assert "LC1D09BD" in mpns
        assert "6ES7214-1AG40-0XB0" in mpns
        assert all(l.source_locator.page_number == 1 for l in result.lines)

    def test_corrupt_pdf_fails_safely(self):
        file_path = SAMPLES_DIR / "corrupt_file.pdf"
        content = file_path.read_bytes()
        parser = get_parser(SourceType.PDF_NATIVE)
        with pytest.raises(DocumentParserError, match="Corrupted or invalid PDF"):
            parser.parse(content, "corrupt_file.pdf")

    def test_scanned_pdf_rejection_when_ocr_disabled(self):
        # A valid empty PDF without text layer simulates a scanned document
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        empty_pdf_bytes = bytes(pdf.output())

        parser = get_parser(SourceType.PDF_NATIVE, allow_ocr=False)
        with pytest.raises(DocumentParserError, match="Scanned or image-only PDF detected"):
            parser.parse(empty_pdf_bytes, "scanned.pdf")


class TestTextAndEmailParser:
    """Verifies deterministic parsing of messy email bodies, vague references, and security inputs."""

    def test_parse_messy_email_quote_request(self):
        file_path = SAMPLES_DIR / "messy_email_quote_request.txt"
        content = file_path.read_bytes()
        parser = get_parser(SourceType.EMAIL_TEXT)
        result = parser.parse(content, "messy_email_quote_request.txt")

        assert result.total_lines_detected == 6
        mpns = [l.requested_mpn for l in result.lines]
        assert "LC1D09BD" in mpns
        assert "6ES7223-1BL32-0XB0" in mpns
        assert "XB4BA31" in mpns
        assert "MY4N-D2-DC24" in mpns
        assert "FAZ-C10/1" in mpns

        # Item 5 is "sensor from last time" -> must be flagged with UNKNOWN_PART_REFERENCE
        vague_line = [l for l in result.lines if l.requested_mpn is None][0]
        assert any(w.code == "UNKNOWN_PART_REFERENCE" for w in vague_line.extraction_warnings)

    def test_adversarial_prompt_injection_safety(self):
        file_path = SAMPLES_DIR / "adversarial_prompt_injection.txt"
        content = file_path.read_bytes()
        parser = get_parser(SourceType.EMAIL_TEXT)
        result = parser.parse(content, "adversarial_prompt_injection.txt")

        # Parsing completes safely as raw strings without executing any injection instruction
        assert result.total_lines_detected >= 3
        # Ensure no arbitrary prices or states were modified
        for line in result.lines:
            assert line.quantity is None or line.quantity > 0
