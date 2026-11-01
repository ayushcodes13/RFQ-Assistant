"""Adversarial security and integrity tests for RFQ Assistant ingestion pipeline.

Validates:
1. Direct upload using /api/rfqs cannot bypass malware scanning.
2. ClamAV daemon failure, malformed response, and protected-mode fail-closed behavior.
3. Transactional rollback on parsing failure leaving zero orphaned cases or files.
4. Parsing preservation for inquiries starting with "Please quote..." or "Urgent:...".
5. Resource exhaustion defenses (PDF pages, CSV rows, XLSX sheets/rows, macro rejection).
"""

import io
import openpyxl
import pytest
from fastapi.testclient import TestClient

from rfq_assistant.api.app import app
from rfq_assistant.ingestion.malware import ClamAVScanner, EICAR_SIGNATURE
from rfq_assistant.ingestion.parsers.base import DocumentParserError
from rfq_assistant.ingestion.parsers.pdf_parser import PDFParser
from rfq_assistant.ingestion.parsers.spreadsheet_parser import SpreadsheetParser
from rfq_assistant.ingestion.parsers.text_parser import TextParser
from rfq_assistant.ingestion.validator import UploadValidationError, validate_file_upload


@pytest.fixture
def client():
    return TestClient(app)


def test_api_rfqs_blocks_eicar_malware_file(client):
    """Direct upload using /api/rfqs must NOT bypass malware scanning (EICAR payload)."""
    files = {"file": ("malicious.txt", io.BytesIO(EICAR_SIGNATURE), "text/plain")}
    response = client.post("/api/rfqs", files=files)
    assert response.status_code == 400
    assert "Malicious attachment quarantined" in response.json()["detail"]


def test_api_rfqs_blocks_eicar_pasted_text(client):
    """Pasted text with EICAR string at /api/rfqs is quarantined and rejected."""
    eicar_str = EICAR_SIGNATURE.decode("latin1")
    data = {"pasted_text": f"Please quote this immediately: {eicar_str}"}
    response = client.post("/api/rfqs", data=data)
    assert response.status_code == 400
    assert "Malicious content quarantined" in response.json()["detail"]


def test_v1_extract_blocks_eicar_attachment(client):
    """V1 extract endpoint also catches and blocks EICAR attachments."""
    files = {"file": ("test_eicar.pdf", io.BytesIO(EICAR_SIGNATURE), "application/pdf")}
    response = client.post("/v1/rfqs/extract", files=files)
    assert response.status_code == 400
    assert "Security alert: Malicious attachment quarantined" in response.json()["detail"]


@pytest.mark.parametrize("endpoint", ["/api/rfqs", "/v1/rfqs/extract"])
def test_rfq_upload_endpoints_reject_oversized_files_before_processing(client, endpoint):
    from rfq_assistant.ingestion.validator import MAX_UPLOAD_BYTES

    payload = b"x" * (MAX_UPLOAD_BYTES + 1)
    response = client.post(
        endpoint,
        files={"file": ("oversized.txt", io.BytesIO(payload), "text/plain")},
    )
    assert response.status_code == 413
    assert "upload limit" in response.json()["detail"]


@pytest.mark.asyncio
async def test_bounded_upload_reader_never_requests_unbounded_bytes():
    from fastapi import HTTPException
    from rfq_assistant.api.app import _read_bounded_upload
    from rfq_assistant.ingestion.validator import MAX_UPLOAD_BYTES

    class UnknownSizeUpload:
        size = None

        def __init__(self):
            self.requested_size = None
            self.closed = False

        async def read(self, size=-1):
            self.requested_size = size
            return b"x" * size

        async def close(self):
            self.closed = True

    upload = UnknownSizeUpload()
    with pytest.raises(HTTPException) as exc_info:
        await _read_bounded_upload(upload)

    assert exc_info.value.status_code == 413
    assert upload.requested_size == MAX_UPLOAD_BYTES + 1
    assert upload.closed


def test_clamav_protected_mode_fail_closed_on_outage():
    """When protected_mode is enabled, daemon unavailability strictly fails closed."""
    # Use invalid port where no daemon is running
    scanner = ClamAVScanner(host="127.0.0.1", port=65534, protected_mode=True, timeout=0.1)
    result = scanner.scan_bytes(b"Clean safe commercial RFQ document text", filename="rfq.txt")
    assert not result.is_clean
    assert result.threat_name == "ClamAV-Daemon-Unavailable"
    assert result.engine == "clamav-fail-closed"


@pytest.mark.parametrize("value", ["1", "true", "yes", "on"])
def test_require_antivirus_accepts_common_true_flags(monkeypatch, value):
    monkeypatch.setenv("REQUIRE_ANTIVIRUS", value)
    scanner = ClamAVScanner(host="127.0.0.1", port=65534, timeout=0.1)
    result = scanner.scan_bytes(b"Synthetic RFQ content")
    assert scanner.protected_mode
    assert not result.is_clean
    assert not result.scanned


def test_clamav_development_fallback_when_unprotected():
    """An offline development fallback must not claim that content was scanned clean."""
    scanner = ClamAVScanner(host="127.0.0.1", port=65534, protected_mode=False, timeout=0.1)
    result = scanner.scan_bytes(b"Clean safe commercial RFQ document text", filename="rfq.txt")
    assert not result.is_clean
    assert not result.scanned
    assert result.engine == "clamav-offline-fallback"


def test_local_unscanned_intake_is_flagged_and_protected_intake_is_blocked(monkeypatch, tmp_path):
    """Local fallback remains usable but marks the case; protected mode blocks it."""
    import importlib
    from types import SimpleNamespace

    from rfq_assistant.cases.manager import CaseManager
    from rfq_assistant.ingestion.storage import DocumentStorage
    from rfq_assistant.matching.catalog import CatalogRepository

    api = importlib.import_module("rfq_assistant.api.app")
    manager = CaseManager(
        CatalogRepository(), storage=DocumentStorage(tmp_path / "uploads")
    )
    monkeypatch.setattr(api, "case_manager", manager)
    monkeypatch.setattr(api, "ASYNC_INGEST_ENABLED", False)
    monkeypatch.setattr(
        api, "clamav_scanner",
        SimpleNamespace(
            protected_mode=False,
            scan_bytes=lambda *_args, **_kwargs: SimpleNamespace(
                is_clean=False, scanned=False, quarantined=False,
                threat_name=None, engine="clamav-offline-fallback",
            ),
        ),
    )
    client = TestClient(api.app)
    response = client.post(
        "/api/rfqs",
        data={"pasted_text": "Please quote 2 EA LC1D09BD Schneider Electric"},
    )
    assert response.status_code == 200
    assert any(
        warning["code"] == "ANTIVIRUS_SCAN_UNAVAILABLE"
        for warning in response.json()["document_warnings"]
    )

    monkeypatch.setattr(api.clamav_scanner, "protected_mode", True)
    blocked = client.post(
        "/api/rfqs",
        data={"pasted_text": "Please quote 2 EA LC1D09BD Schneider Electric"},
    )
    assert blocked.status_code == 400
    assert "scan unavailable" in blocked.json()["detail"].lower()
    assert len(manager.list_cases()) == 1


def test_parsing_failure_keeps_source_and_failed_case_for_manual_review(tmp_path, monkeypatch):
    """A validated upload stays available when parsing fails, with an explicit failed case."""
    # Mock parser to raise DocumentParserError
    from rfq_assistant.ingestion.parsers import base

    class BrokenParser(base.BaseDocumentParser):
        def parse(self, content: bytes, filename: str):
            raise DocumentParserError("Parser failed due to unrecoverable internal format corruption")

    monkeypatch.setattr("rfq_assistant.cases.manager.get_parser", lambda src: BrokenParser())

    from rfq_assistant.cases.manager import CaseManager
    from rfq_assistant.ingestion.storage import DocumentStorage
    from rfq_assistant.matching.catalog import CatalogRepository

    manager = CaseManager(catalog=CatalogRepository(), storage=DocumentStorage(base_dir=tmp_path))
    valid_csv_content = b"Part Number,Quantity\nLC1D09BD,10\n"

    case = manager.create_case_from_upload(
        filename="test_corrupt_stream.csv",
        content=valid_csv_content,
        title="Manual review required",
    )

    assert case.status.value == "FAILED"
    assert any("Parser failed" in warning.message for warning in case.document_warnings)
    assert manager.storage.get_file(case.case_id, "test_corrupt_stream.csv") == valid_csv_content
    assert manager.get_lines(case.case_id) == []


def test_text_parser_preserves_please_quote_and_urgent_inquiries():
    """Requests starting with 'Please quote...' or 'Urgent:...' must not be silently discarded."""
    text_parser = TextParser()
    raw_email = (
        "Dear Sales Team,\n"
        "Please quote 10 pcs LC1D09BD Schneider Electric 24VDC\n"
        "Urgent: 5 pcs 6ES7214-1AG40-0XB0 Siemens S7-1200 CPU\n"
        "Please provide pricing for: 20 pcs E2E-X3D1-N Omron Proximity Sensor\n"
        "Best regards,\n"
        "Operations Dept\n"
    )

    result = text_parser.parse(raw_email.encode("utf-8"), "email.txt")
    assert len(result.lines) == 3, f"Expected 3 lines, got {len(result.lines)}"

    # Check line 1
    assert result.lines[0].requested_mpn == "LC1D09BD"
    assert result.lines[0].quantity == 10.0

    # Check line 2
    assert "6ES7214-1AG40-0XB0" in result.lines[1].raw_text
    assert result.lines[1].quantity == 5.0

    # Check line 3
    assert "E2E-X3D1-N" in result.lines[2].raw_text
    assert result.lines[2].quantity == 20.0


def test_pdf_page_limit_enforced():
    """PDF exceeding 50 pages must be rejected with DocumentParserError."""
    # Create synthetic PDF in memory with 55 empty pages using pypdf
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(55):
        writer.add_blank_page(width=100, height=100)

    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    parser = PDFParser()
    with pytest.raises(DocumentParserError) as exc_info:
        parser.parse(pdf_bytes, "oversized.pdf")

    assert "exceeds maximum permitted limit (50 pages)" in str(exc_info.value)


def test_spreadsheet_row_limit_enforced():
    """CSV exceeding 5000 rows must be rejected with DocumentParserError."""
    header = "Part Number,Quantity,Description\n"
    rows = [f"PART-{i},1,Desc {i}\n" for i in range(5005)]
    csv_bytes = (header + "".join(rows)).encode("utf-8")

    parser = SpreadsheetParser()
    with pytest.raises(DocumentParserError) as exc_info:
        parser.parse(csv_bytes, "oversized.csv")

    assert "exceeds maximum permitted limit (5000 rows)" in str(exc_info.value)


def test_spreadsheet_sheet_limit_enforced():
    """XLSX workbook with more than 20 sheets must be rejected with DocumentParserError."""
    wb = openpyxl.Workbook()
    for i in range(25):
        wb.create_sheet(title=f"Sheet_{i}")

    buf = io.BytesIO()
    wb.save(buf)
    xlsx_bytes = buf.getvalue()

    parser = SpreadsheetParser()
    with pytest.raises(DocumentParserError) as exc_info:
        parser.parse(xlsx_bytes, "too_many_sheets.xlsx")

    assert "exceeds maximum permitted limit (20 sheets)" in str(exc_info.value)


def test_macro_enabled_spreadsheet_rejected_by_validator():
    """Macro-enabled extensions (.xlsm) must be rejected before parsing."""
    with pytest.raises(UploadValidationError) as exc_info:
        validate_file_upload("bom_with_vba.xlsm", b"Fake macro binary content")

    assert "Macro-enabled spreadsheets ('.xlsm') are prohibited" in str(exc_info.value)
