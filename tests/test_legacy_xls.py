"""Legacy XLS conversion stays bounded and does not inherit application secrets."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired

import openpyxl
import pytest

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.parsers.base import DocumentParserError
from rfq_assistant.ingestion.parsers.spreadsheet_parser import SpreadsheetParser
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.ingestion.validator import UploadValidationError, validate_file_upload
from rfq_assistant.ingestion.xls_conversion import (
    LegacyXLSConversionError,
    convert_legacy_xls,
)
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.schemas.enums import CaseStatus, SourceType
from rfq_assistant.schemas.models import CatalogItem


OLE_HEADER = bytes.fromhex("D0CF11E0A1B11AE1")


def _synthetic_xlsx() -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "RFQ"
    sheet.append(["Part Number", "Manufacturer", "Quantity", "Description"])
    sheet.append(["LC1D09BD", "Schneider Electric", 4, "Synthetic contactor"])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def _mock_converter(output_bytes: bytes, seen: dict):
    def run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        profile_arg = next(arg for arg in command if arg.startswith("-env:UserInstallation=file://"))
        profile_path = Path(profile_arg.split("=", 1)[1].removeprefix("file://"))
        seen["macro_security_config"] = (
            profile_path / "user" / "registrymodifications.xcu"
        ).read_text(encoding="utf-8")
        source = Path(command[-1])
        output_dir = Path(command[command.index("--outdir") + 1])
        (output_dir / f"{source.stem}.xlsx").write_bytes(output_bytes)
        return CompletedProcess(command, 0)
    return run


def test_validator_recognizes_legacy_xls_and_rejects_fake_extension():
    filename, source_type, digest = validate_file_upload("quote.xls", OLE_HEADER + b"synthetic")
    assert filename == "quote.xls"
    assert source_type == SourceType.XLSX
    assert len(digest) == 64
    with pytest.raises(UploadValidationError, match="legacy Excel"):
        validate_file_upload("fake.xls", b"not an xls file")


def test_converter_uses_isolated_profile_and_does_not_inherit_api_keys(monkeypatch):
    seen = {}
    monkeypatch.setenv("RFQ_LLM_API_KEY", "must-not-enter-converter-process")
    monkeypatch.setattr(
        "rfq_assistant.ingestion.xls_conversion.subprocess.run",
        _mock_converter(_synthetic_xlsx(), seen),
    )

    result = convert_legacy_xls(OLE_HEADER + b"synthetic", converter="/fake/soffice")
    assert result.startswith(b"PK")
    kwargs = seen["kwargs"]
    assert kwargs["timeout"] == 30
    assert kwargs["stdin"] is not None
    assert kwargs["env"]["HOME"] != str(Path.home())
    assert "RFQ_LLM_API_KEY" not in kwargs["env"]
    assert any(arg.startswith("-env:UserInstallation=file://") for arg in seen["command"])
    assert "MacroSecurityLevel" in seen["macro_security_config"]
    assert "<value>3</value>" in seen["macro_security_config"]


def test_parser_converts_and_retains_original_filename_with_review_warning(monkeypatch):
    monkeypatch.setattr("rfq_assistant.ingestion.xls_conversion.shutil.which", lambda _: "/usr/bin/libreoffice")
    monkeypatch.setattr(
        "rfq_assistant.ingestion.xls_conversion.subprocess.run",
        _mock_converter(_synthetic_xlsx(), {}),
    )
    result = SpreadsheetParser().parse(OLE_HEADER + b"synthetic", "customer_quote.xls")
    assert len(result.lines) == 1
    assert result.lines[0].requested_mpn == "LC1D09BD"
    assert result.lines[0].source_locator.file_name == "customer_quote.xls"
    assert result.warnings[0].code == "LEGACY_XLS_CONVERTED"


def test_legacy_xls_upload_runs_through_case_matching_and_keeps_original(tmp_path, monkeypatch):
    monkeypatch.setattr("rfq_assistant.ingestion.xls_conversion.shutil.which", lambda _: "/usr/bin/libreoffice")
    monkeypatch.setattr(
        "rfq_assistant.ingestion.xls_conversion.subprocess.run",
        _mock_converter(_synthetic_xlsx(), {}),
    )
    catalog = CatalogRepository()
    catalog.add_item(CatalogItem(
        internal_sku="SYN-LC1D09BD",
        manufacturer="Schneider Electric",
        manufacturer_part_number="LC1D09BD",
        description="Synthetic contactor",
    ))
    manager = CaseManager(catalog, storage=DocumentStorage(tmp_path / "store"))
    original = OLE_HEADER + b"synthetic legacy workbook"

    case = manager.create_case_from_upload("legacy_quote.xls", original)
    rows = manager.get_lines(case.case_id)

    assert case.status == CaseStatus.NEEDS_REVIEW
    assert case.source_file.file_name == "legacy_quote.xls"
    assert manager.storage.get_file(case.case_id, "legacy_quote.xls") == original
    assert len(rows) == 1
    assert rows[0].match_status.value == "EXACT_MATCH"
    assert rows[0].source_locator.file_name == "legacy_quote.xls"
    assert any(w.code == "LEGACY_XLS_CONVERTED" for w in case.document_warnings)


def test_converter_timeout_fails_closed(monkeypatch):
    def timeout(*args, **kwargs):
        raise TimeoutExpired(args[0], timeout=30)

    monkeypatch.setattr("rfq_assistant.ingestion.xls_conversion.subprocess.run", timeout)
    with pytest.raises(LegacyXLSConversionError, match="30-second"):
        convert_legacy_xls(OLE_HEADER + b"synthetic", converter="/fake/soffice")


def test_converter_rejects_macro_content_in_result(monkeypatch):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/vbaProject.bin", b"synthetic macro")
    monkeypatch.setattr(
        "rfq_assistant.ingestion.xls_conversion.subprocess.run",
        _mock_converter(output.getvalue(), {}),
    )
    with pytest.raises(LegacyXLSConversionError, match="macro"):
        convert_legacy_xls(OLE_HEADER + b"synthetic", converter="/fake/soffice")


def test_missing_converter_fails_with_actionable_error(monkeypatch):
    monkeypatch.setattr("rfq_assistant.ingestion.xls_conversion.shutil.which", lambda _: None)
    with pytest.raises(DocumentParserError, match="LibreOffice is not installed"):
        SpreadsheetParser().parse(OLE_HEADER + b"synthetic", "legacy.xls")
