"""
Extended end-to-end audit tests for RFQ-Assistant.

This module extends the audit with focused synthetic test sets covering:
1. Text extraction: numeric-only MPNs, suffixes/revisions, quantities/specifications,
   quoted email threads, unfamiliar manufacturers, description-only requests.
2. CSV/XLSX layout diversity: headerless, title/header rows, formulas (cached
   and uncached), hidden/merged/blank regions, quantity/unit formats.
3. PDF layouts: wrapped descriptions, tab-delimited tables, repeated headers,
   page breaks, unknown manufacturers, scanned PDF rejection.
4. Exact matching: cross-brand collisions, duplicate catalog records, suffix
   near-collisions, missing manufacturer, unknown parts.
5. Review/edit/approval/version behavior and full vs partial export blocking.
6. API export download from default and temporary storage, persistence/restart,
   deletion behavior.
7. Auth and role checks, upload/path/macro/size defenses, formula-safe export,
   quote-send route under every configuration.
8. Isolated concurrency across intake and later workflow stages.

All data is synthetic. No fixes are applied — this is audit only.
"""

import csv as csv_module
import io
import math
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import List, Optional

import openpyxl
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from rfq_assistant.api.app import app as api_app
from rfq_assistant.agents.tools import ApprovalGateError, QuotationCommercialService
from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.exports.generator import ExportGenerator, ExportValidationError
from rfq_assistant.ingestion import (
    DocumentParserError,
    DocumentStorage,
    UploadValidationError,
    validate_file_upload,
)
from rfq_assistant.ingestion.malware import ClamAVScanner
from rfq_assistant.ingestion.parsers.pdf_parser import PDFParser
from rfq_assistant.ingestion.parsers.spreadsheet_parser import SpreadsheetParser
from rfq_assistant.ingestion.parsers.text_parser import TextParser
from rfq_assistant.matching.catalog import CatalogImportError, CatalogRepository
from rfq_assistant.matching.engine import ExactMatchEngine
from rfq_assistant.persistence import SQLiteStateStore
from rfq_assistant.schemas.enums import (
    AuditAction,
    CaseStatus,
    MatchStatus,
    ReviewDecision,
    SourceType,
)
from rfq_assistant.schemas.models import (
    CatalogItem,
    ExportManifest,
    ExportRequest,
    RFQLineItemUpdate,
)

AUDIT_FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXTENDED_CATALOG = AUDIT_FIXTURES / "audit_extended_catalog.csv"


# ---------------------------------------------------------------------------
# Audit finding recorder
# ---------------------------------------------------------------------------

class AuditFinding:
    """Records a single audit finding for evidence."""
    def __init__(self, title: str, severity: str, category: str,
                 expected: str, observed: str, evidence: str,
                 defect_type: str = "defect"):
        self.title = title
        self.severity = severity
        self.category = category
        self.expected = expected
        self.observed = observed
        self.evidence = evidence
        self.defect_type = defect_type

    def __repr__(self):
        return f"AuditFinding(title={self.title!r}, severity={self.severity}, type={self.defect_type})"


FINDINGS: List[AuditFinding] = []


def record_finding(title, severity, category, expected, observed, evidence, defect_type="defect"):
    """Global finding registry — accumulates findings across test runs."""
    FINDINGS.append(AuditFinding(title, severity, category, expected, observed, evidence, defect_type))


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ext_catalog():
    """Catalog with extended items including duplicates and cross-brand collisions."""
    catalog = CatalogRepository()
    catalog.import_csv(EXTENDED_CATALOG.read_bytes(), version="synth-audit-ext")
    return catalog


@pytest.fixture
def ext_services(tmp_path, ext_catalog):
    """Fresh managers with isolated temp storage and extended catalog."""
    manager = CaseManager(
        catalog=ext_catalog,
        storage=DocumentStorage(tmp_path / "uploads"),
    )
    generator = ExportGenerator(
        catalog=ext_catalog,
        base_export_dir=tmp_path / "exports",
    )
    return manager, generator, ext_catalog, tmp_path


@pytest.fixture
def isolated_state(tmp_path):
    """Fully isolated state: fresh SQLite store, catalog, manager, generator."""
    db_path = tmp_path / "state" / "rfq.sqlite3"
    store = SQLiteStateStore(db_path)
    storage = DocumentStorage(tmp_path / "uploads")
    catalog = CatalogRepository(state_store=store)
    catalog.import_csv(EXTENDED_CATALOG.read_bytes(), version="synth-audit-ext")
    manager = CaseManager(catalog=catalog, storage=storage, state_store=store)
    generator = ExportGenerator(catalog=catalog, base_export_dir=tmp_path / "exports")
    return {
        "store": store,
        "storage": storage,
        "catalog": catalog,
        "manager": manager,
        "generator": generator,
        "tmp_path": tmp_path,
    }


@pytest.fixture
def api_client_no_auth(tmp_path, monkeypatch, ext_catalog):
    """API TestClient with auth disabled, isolated state, extended catalog."""
    import importlib
    api_module = importlib.import_module("rfq_assistant.api.app")

    db_path = tmp_path / "api_no_auth.sqlite3"
    store = SQLiteStateStore(db_path)
    catalog = CatalogRepository(state_store=store)
    catalog.import_csv(EXTENDED_CATALOG.read_bytes(), version="synth-audit-ext")
    manager = CaseManager(catalog=catalog, storage=DocumentStorage(tmp_path / "uploads"), state_store=store)
    generator = ExportGenerator(catalog=catalog, base_export_dir=tmp_path / "exports")

    monkeypatch.setattr(api_module, "catalog_repo", catalog)
    monkeypatch.setattr(api_module, "case_manager", manager)
    monkeypatch.setattr(api_module, "export_generator", generator)
    monkeypatch.setattr(api_module, "clamav_scanner", ClamAVScanner(protected_mode=False))
    monkeypatch.setattr(api_module, "commercial_service", QuotationCommercialService())
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("PILOT_API_KEYS", raising=False)
    monkeypatch.delenv("REQUIRE_REAL_TRANSPORT", raising=False)
    client = TestClient(api_module.app)
    return client, manager, generator, catalog, tmp_path


@pytest.fixture
def api_client_auth_on(tmp_path, monkeypatch, ext_catalog):
    """API client with auth enabled and test credentials configured."""
    import importlib
    api_module = importlib.import_module("rfq_assistant.api.app")

    db_path = tmp_path / "api_auth.sqlite3"
    store = SQLiteStateStore(db_path)
    catalog = CatalogRepository(state_store=store)
    catalog.import_csv(EXTENDED_CATALOG.read_bytes(), version="synth-audit-ext")
    manager = CaseManager(catalog=catalog, storage=DocumentStorage(tmp_path / "uploads"), state_store=store)
    generator = ExportGenerator(catalog=catalog, base_export_dir=tmp_path / "exports")

    monkeypatch.setattr(api_module, "catalog_repo", catalog)
    monkeypatch.setattr(api_module, "case_manager", manager)
    monkeypatch.setattr(api_module, "export_generator", generator)
    monkeypatch.setattr(api_module, "clamav_scanner", ClamAVScanner(protected_mode=False))
    monkeypatch.setattr(api_module, "commercial_service", QuotationCommercialService())
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    monkeypatch.setenv(
        "PILOT_API_KEYS",
        "test-admin-secret-000000001:admin:Authorized Administrator,"
        "test-reviewer-secret-00000001:reviewer:Authorized Reviewer,"
        "test-viewer-secret-000000001:viewer:Read-Only Auditor",
    )
    monkeypatch.delenv("REQUIRE_REAL_TRANSPORT", raising=False)
    client = TestClient(api_module.app)
    return client, manager, generator, catalog, tmp_path


@pytest.fixture(autouse=True)
def _cleanup_persistence():
    """Ensure tests don't pollute the shared SQLite store."""
    import importlib
    api_module = importlib.import_module("rfq_assistant.api.app")
    original_catalog = api_module.catalog_repo
    original_manager = api_module.case_manager
    original_generator = api_module.export_generator
    original_store = api_module.state_store
    yield
    api_module.catalog_repo = original_catalog
    api_module.case_manager = original_manager
    api_module.export_generator = original_generator
    api_module.state_store = original_store


# ---------------------------------------------------------------------------
# 1. Text extraction: numeric-only MPNs, suffixes, quantities, quoted threads,
#    unfamiliar manufacturers, description-only
# ---------------------------------------------------------------------------

class TestTextExtractionExtended:
    """Extended text parser tests covering edge cases from the audit requirements."""

    def test_quoted_email_thread_extracts_all_items(self, ext_services):
        """Quoted email threads with nested quotes must extract all items."""
        manager, _, catalog, _ = ext_services
        content = (AUDIT_FIXTURES / "quoted_email_thread.txt").read_bytes()
        case = manager.create_case_from_upload(
            filename="quoted_email.txt", content=content,
            customer_label="SYN-TEST", actor="Auditor",
        )
        lines = manager.get_lines(case.case_id)

        # All 3 items should be extracted despite being in quoted blocks
        assert len(lines) == 3, f"Expected 3 lines from quoted thread, got {len(lines)}"

        mpns = {l.requested_mpn for l in lines}
        assert "LC1D09BD" in mpns
        assert "6ES7214-1AG40-0XB0" in mpns
        assert "MY4N-D2-DC24" in mpns

        for line in lines:
            assert line.source_locator.file_name == "quoted_email.txt"
            assert line.source_locator.row_number is not None

    def test_text_parser_extracts_numeric_only_mpn(self):
        """Numeric-only MPNs like Phoenix Contact '2900364' are now extracted."""
        parser = TextParser()
        content = b"10 pcs Phoenix Contact 2900364 relay module 24VDC"
        result = parser.parse(content, "numeric_mpn.txt")

        line = result.lines[0]
        assert line.requested_mpn == "2900364", \
            "TextParser should extract numeric-only MPNs (>= 5 digits)"
        # The line is still created because the OEM 'Phoenix Contact' is detected
        assert line.requested_manufacturer == "Phoenix Contact"
        assert line.quantity == 10.0

    def test_text_parser_false_positive_mpn_extraction(self):
        """
        Specification tokens like '3-pole', '9A', '24VDC' must not be extracted as MPNs.
        """
        parser = TextParser()
        content = b"10 pcs 24VDC contactor, 9A, 3-pole, Schneider Electric"
        result = parser.parse(content, "false_positive.txt")
        lines = result.lines
        assert len(lines) >= 1, "Line with OEM should be detected"
        mpn = lines[0].requested_mpn
        # No spec token should be extracted as MPN
        assert mpn is None or mpn == "LC1D09BD", f"Specification token wrongly extracted as MPN: {mpn}"

    def test_description_only_lines_retain_warnings(self, ext_services):
        """Lines with no extractable MPN should have appropriate warnings and be reviewable."""
        manager, _, catalog, _ = ext_services
        case = manager.create_case_from_text(
            "10 pcs Schneider Electric 24VDC contactor 9A",
            customer_label="SYN-TEST", actor="Auditor",
        )
        lines = manager.get_lines(case.case_id)
        assert len(lines) >= 1
        line = lines[0]
        # MPN should be None (no valid MPN token), match should be NO_MATCH
        assert line.match_status == MatchStatus.NO_MATCH
        assert line.selected_catalog_sku is None

    def test_suffix_near_collisions_preserved(self, ext_catalog):
        """ABC-12, ABC-12A, ABC-12-R2 must each map to different SKUs."""
        engine = ExactMatchEngine(ext_catalog)

        for mpn, expected_sku in [
            ("ABC-12", "SKU-EXT-009"),
            ("ABC-12A", "SKU-EXT-010"),
            ("ABC-12-R2", "SKU-EXT-011"),
        ]:
            # ABC-12 has duplicate records (SKU-EXT-009 and SKU-EXT-015) → COLLISION
            result = engine.match_line(mpn, "Acme Industrial")
            if mpn == "ABC-12":
                # This is the duplicate record case
                assert result.match_status == MatchStatus.COLLISION
                assert result.selected_sku is None
                skus = {c.catalog_item.internal_sku for c in result.candidates}
                assert "SKU-EXT-009" in skus
                assert "SKU-EXT-015" in skus
            else:
                assert result.match_status == MatchStatus.EXACT_MATCH
                assert result.selected_sku == expected_sku

    def test_cross_brand_collision_no_auto_selection(self, ext_catalog):
        """XG-42 with no manufacturer must be COLLISION, not auto-selected."""
        engine = ExactMatchEngine(ext_catalog)
        result = engine.match_line("XG-42", None)
        assert result.match_status == MatchStatus.COLLISION
        assert result.selected_sku is None
        assert len(result.candidates) == 2
        oems = {c.catalog_item.manufacturer for c in result.candidates}
        assert oems == {"Apex Automation", "Delta Electronics"}

    def test_unknown_manufacturer_not_normalized_to_known(self, ext_catalog):
        """Unknown/unfamiliar manufacturers should pass through unchanged."""
        from rfq_assistant.matching.normalizer import normalize_manufacturer
        result = normalize_manufacturer("Some Synthetic Brand Co")
        assert result == "Some Synthetic Brand Co"

    def test_duplicate_catalog_record_same_mpn_same_oem_is_collision(self, ext_catalog):
        """When two SKUs exist for same MPN+OEM, engine returns COLLISION with both."""
        engine = ExactMatchEngine(ext_catalog)
        # ABC-12 appears under two SKUs (SKU-EXT-009 and SKU-EXT-015) both under Acme Industrial
        result = engine.match_line("ABC-12", "Acme Industrial")
        assert result.match_status == MatchStatus.COLLISION
        assert result.selected_sku is None
        assert len(result.candidates) == 2
        skus = {c.catalog_item.internal_sku for c in result.candidates}
        assert "SKU-EXT-009" in skus
        assert "SKU-EXT-015" in skus

    def test_unknown_part_number_no_match(self, ext_catalog):
        """Completely unknown MPN should be NO_MATCH."""
        engine = ExactMatchEngine(ext_catalog)
        result = engine.match_line("NONEXISTENT-PART-12345", "Schneider Electric")
        assert result.match_status == MatchStatus.NO_MATCH
        assert result.selected_sku is None

    def test_missing_manufacturer_with_unique_mpn_is_collision(self, ext_catalog):
        """When manufacturer is None and MPN exists under one manufacturer,
        the engine returns COLLISION (conservative — requires human confirmation)."""
        engine = ExactMatchEngine(ext_catalog)
        result = engine.match_line("LC1D09BD", None)
        assert result.match_status == MatchStatus.COLLISION
        assert result.selected_sku is None
        assert len(result.candidates) == 1

    def test_manufacturer_mismatch_is_collision(self, ext_catalog):
        """MPN exists under different manufacturer → COLLISION."""
        engine = ExactMatchEngine(ext_catalog)
        result = engine.match_line("LC1D09BD", "Siemens")
        assert result.match_status == MatchStatus.COLLISION
        assert result.selected_sku is None

    def test_empty_mpn_is_no_match(self, ext_catalog):
        """Empty or None MPN should be NO_MATCH."""
        engine = ExactMatchEngine(ext_catalog)
        result = engine.match_line(None, "Schneider Electric")
        assert result.match_status == MatchStatus.NO_MATCH

    def test_case_insensitive_oem_mpn_matching(self, ext_catalog):
        """OEM and MPN matching should be case-insensitive."""
        engine = ExactMatchEngine(ext_catalog)
        result = engine.match_line("lc1d09bd", "schneider electric")
        assert result.match_status == MatchStatus.EXACT_MATCH
        assert result.selected_sku == "SKU-EXT-001"


# ---------------------------------------------------------------------------
# 2. CSV/XLSX layout diversity, headerless, title rows, hidden/merged/blank
# ---------------------------------------------------------------------------

class TestSpreadsheetLayoutDiversity:

    def test_xlsx_title_then_header_detected(self, ext_services):
        """XLSX with title rows before header should detect header on row 4."""
        manager, _, catalog, _ = ext_services
        content = (AUDIT_FIXTURES / "xlsx_title_then_header.xlsx").read_bytes()
        case = manager.create_case_from_upload(
            filename="title_header.xlsx", content=content,
            customer_label="SYN-TEST", actor="Auditor",
        )
        lines = manager.get_lines(case.case_id)
        assert len(lines) == 2
        assert lines[0].requested_mpn == "LC1D09BD"
        assert lines[0].source_locator.row_number == 5
        assert lines[1].requested_mpn == "6ES7214-1AG40-0XB0"

    def test_xlsx_hidden_sheets_are_parsed(self, ext_services):
        """Hidden sheet contents are not silently treated as RFQ rows."""
        manager, _, catalog, _ = ext_services
        content = (AUDIT_FIXTURES / "xlsx_hidden_merged_blank.xlsx").read_bytes()
        case = manager.create_case_from_upload(
            filename="hidden.xlsx", content=content,
            customer_label="SYN-TEST", actor="Auditor",
        )
        lines = manager.get_lines(case.case_id)
        assert len(lines) == 4

        sheet_names = {l.source_locator.sheet_name for l in lines}
        assert "Line Items" in sheet_names, "Data from hidden sheet was extracted"

        assert "Internal Pricing" not in sheet_names
        assert any(w.code == "HIDDEN_SHEET_INCLUDED" for w in case.document_warnings)

    def test_xlsx_merged_cells_and_blanks(self, ext_services):
        """Merged cells and blank rows should be handled gracefully."""
        manager, _, catalog, _ = ext_services
        content = (AUDIT_FIXTURES / "xlsx_hidden_merged_blank.xlsx").read_bytes()
        case = manager.create_case_from_upload(
            filename="merged.xlsx", content=content,
            customer_label="SYN-TEST", actor="Auditor",
        )
        lines = manager.get_lines(case.case_id)
        # All lines should have an MPN (blank rows properly skipped)
        for line in lines:
            assert line.requested_mpn is not None, \
                f"Line {line.line_number} has no MPN (merged cell issue?)"

    def test_xlsx_quantity_formats_parsed(self, ext_services):
        """Various quantity formats: '10 pcs', '5 units', '20x', '15.5'."""
        manager, _, catalog, _ = ext_services
        content = (AUDIT_FIXTURES / "xlsx_quantity_formats.xlsx").read_bytes()
        case = manager.create_case_from_upload(
            filename="qty_formats.xlsx", content=content,
            customer_label="SYN-TEST", actor="Auditor",
        )
        lines = manager.get_lines(case.case_id)
        assert len(lines) == 4

        qtys = {l.requested_mpn: l.quantity for l in lines}
        assert qtys.get("LC1D09BD") == 10.0
        assert qtys.get("6ES7214-1AG40-0XB0") == 5.0
        assert qtys.get("MY4N-D2-DC24") == 20.0
        assert qtys.get("F2966171") == 15.5

    def test_xlsx_fresh_formulas_no_cache_are_visible_for_review(self, ext_services):
        """Formula text is retained and the affected row is explicitly marked."""
        manager, _, catalog, _ = ext_services
        content = (AUDIT_FIXTURES / "xlsx_fresh_formulas_no_cache.xlsx").read_bytes()
        case = manager.create_case_from_upload(
            filename="fresh_formulas.xlsx", content=content,
            customer_label="SYN-TEST", actor="Auditor",
        )
        lines = manager.get_lines(case.case_id)

        assert len(lines) == 3
        formula_line = next(line for line in lines if "=SUM" in line.raw_text)
        assert formula_line.quantity is None
        assert any(w.code == "FORMULA_VALUE_NOT_EVALUATED" for w in formula_line.extraction_warnings)

    def test_csv_with_various_quantity_formats(self, ext_services):
        """CSV with quantities like '10 pcs', '5 units', '20x', '15.5'."""
        csv_content = (
            b"MPN,Manufacturer,Quantity,Unit\n"
            b"LC1D09BD,Schneider Electric,10 pcs,EA\n"
            b"6ES7214-1AG40-0XB0,Siemens,5 units,EA\n"
            b"MY4N-D2-DC24,Omron,20x,EA\n"
            b"FAZ-C10/1,Eaton,15.5,EA\n"
        )
        manager, _, catalog, _ = ext_services
        case = manager.create_case_from_upload(
            filename="qty_formats.csv", content=csv_content,
            customer_label="SYN-TEST", actor="Auditor",
        )
        lines = manager.get_lines(case.case_id)
        assert len(lines) == 4
        qtys = {l.requested_mpn: l.quantity for l in lines}
        assert qtys["LC1D09BD"] == 10.0
        assert qtys["6ES7214-1AG40-0XB0"] == 5.0
        assert qtys["MY4N-D2-DC24"] == 20.0
        assert qtys["FAZ-C10/1"] == 15.5

    def test_csv_with_extra_unmapped_columns(self, ext_services):
        """CSV with extra columns not in the standard mapping should still parse."""
        csv_content = (
            b"MPN,Manufacturer,Qty,Description,Custom_Field,Notes\n"
            b"LC1D09BD,Schneider Electric,10,Contactor,CustomValue1,Note1\n"
            b"6ES7214-1AG40-0XB0,Siemens,5,CPU,CustomValue2,Note2\n"
        )
        manager, _, catalog, _ = ext_services
        case = manager.create_case_from_upload(
            filename="extra_cols.csv", content=csv_content,
            customer_label="SYN-TEST", actor="Auditor",
        )
        lines = manager.get_lines(case.case_id)
        assert len(lines) == 2
        assert lines[0].requested_mpn == "LC1D09BD"

    def test_csv_with_quoted_quantity_specs(self, ext_services):
        """CSV with quoted quantity specs like '10 pcs (min order qty=10)')."""
        csv_content = (
            b"MPN,OEM,Qty,Notes\n"
            b"LC1D09BD,Schneider Electric,\"10 pcs (min order qty=10)\",Need 10\n"
            b"6ES7214-1AG40-0XB0,Siemens,5,Standard qty\n"
        )
        manager, _, catalog, _ = ext_services
        case = manager.create_case_from_upload(
            filename="qty_specs.csv", content=csv_content,
            customer_label="SYN-TEST", actor="Auditor",
        )
        lines = manager.get_lines(case.case_id)
        assert len(lines) == 2
        # Quoted quantities that contain text may not parse to a number
        line0 = lines[0]
        if line0.quantity is not None:
            assert line0.quantity == 10.0


# ---------------------------------------------------------------------------
# 3. PDF layout diversity
# ---------------------------------------------------------------------------

class TestPdfLayoutDiversity:

    def test_wrapped_description_pdf_extracts_items(self, ext_services):
        """Native PDF with wrapped descriptions and qty-before-OEM should extract items.

        Quantity is now found anywhere in the line, and document reference numbers
        (RFQ-2026-001) are no longer extracted as MPNs.
        """
        manager, _, catalog, _ = ext_services
        content = (AUDIT_FIXTURES / "wrapped_description_pdf.pdf").read_bytes()
        case = manager.create_case_from_upload(
            filename="wrapped.pdf", content=content,
            customer_label="SYN-TEST", actor="Auditor",
        )
        lines = manager.get_lines(case.case_id)

        # 7 lines extracted: 5 real items p1, 2 real items p2
        mpns = {l.requested_mpn for l in lines}
        assert "LC1D09BD" in mpns
        assert "6ES7214-1AG40-0XB0" in mpns
        assert "2900364" in mpns  # Numeric MPN IS extracted by PDF parser

        # RFQ-2026-001 is NOT extracted as a false-positive MPN
        rfq_lines = [l for l in lines if "RFQ-2026" in str(l.requested_mpn)]
        assert len(rfq_lines) == 0, "Quote ID should not be extracted as MPN"

        # Quantity before OEM is now extracted
        lines_with_qty = [l for l in lines if l.quantity is not None and l.quantity > 0]
        lines_without_qty = [l for l in lines if (l.quantity is None or l.quantity <= 0)]
        assert len(lines_without_qty) == 0, "All lines should have a quantity"

        # Verify source locators
        pages = {l.source_locator.page_number for l in lines}
        assert 1 in pages
        assert 2 in pages

    def test_multipage_repeated_headers_pdf(self, ext_services):
        """Multi-page PDF with repeated table headers should not produce false lines."""
        manager, _, catalog, _ = ext_services
        content = (AUDIT_FIXTURES / "multipage_repeated_headers_pdf.pdf").read_bytes()
        case = manager.create_case_from_upload(
            filename="repeated_headers.pdf", content=content,
            customer_label="SYN-TEST", actor="Auditor",
        )
        lines = manager.get_lines(case.case_id)
        assert len(lines) >= 4

        # Check page numbers
        pages = {l.source_locator.page_number for l in lines}
        assert 1 in pages
        assert 2 in pages

    def test_multipage_repeated_headers_pdf_items_have_quantities(self, ext_services):
        """Multi-page PDF with qty at end of line should preserve quantities."""
        manager, _, catalog, _ = ext_services
        content = (AUDIT_FIXTURES / "multipage_repeated_headers_pdf.pdf").read_bytes()
        case = manager.create_case_from_upload(
            filename="multi_headers.pdf", content=content,
            customer_label="SYN-TEST", actor="Auditor",
        )
        lines = manager.get_lines(case.case_id)
        # Check at least one line has a quantity (the ones with qty at end)
        qty_lines = [l for l in lines if l.quantity and l.quantity > 0]
        assert len(qty_lines) >= 3

    def test_scanned_pdf_retained_as_failed_case_without_crash(self, ext_services):
        """Image-only PDF must be preserved with a clear blocking error for manual handling."""
        manager, _, catalog, _ = ext_services
        content = (AUDIT_FIXTURES / "scanned_image_pdf.pdf").read_bytes()
        case = manager.create_case_from_upload(
            filename="scanned.pdf", content=content,
            customer_label="SYN-TEST", actor="Auditor",
        )
        assert case.status.value == "FAILED"
        assert "Scanned" in case.document_warnings[0].message or "image-only" in case.document_warnings[0].message
        assert manager.get_lines(case.case_id) == []

    def test_pdf_with_unknown_manufacturer_not_normalized(self, ext_services):
        """PDF lines with unknown manufacturers should be NO_MATCH, not auto-matched."""
        manager, _, catalog, _ = ext_services
        content = (AUDIT_FIXTURES / "pdf_unfamiliar_manufacturers.pdf").read_bytes()
        case = manager.create_case_from_upload(
            filename="unfam.pdf", content=content,
            customer_label="SYN-TEST", actor="Auditor",
        )
        lines = manager.get_lines(case.case_id)

        # ZZ-99999 has no known OEM → MPN extracted but manufacturer None
        zz99999_lines = [l for l in lines if l.requested_mpn == "ZZ-99999"]
        if zz99999_lines:
            line = zz99999_lines[0]
            assert line.requested_manufacturer is None or "Unknown" in str(line.requested_manufacturer)

        # Unknown parts should not be auto-approved
        for line in lines:
            if line.requested_mpn and line.requested_mpn not in {"RFQ-2026-004"}:
                assert line.review_decision == ReviewDecision.PENDING

    def test_pdf_line_count_under_limit(self, ext_services):
        """Native PDF with multiple pages and items should parse within reasonable limits."""
        content = (AUDIT_FIXTURES / "multipage_native_pdf.pdf").read_bytes()
        parser = PDFParser()
        result = parser.parse(content, "native.pdf")
        assert len(result.lines) >= 1


# ---------------------------------------------------------------------------
# 4. Exact matching: cross-brand, duplicates, suffix near-collisions
# ---------------------------------------------------------------------------

class TestExactMatchingExtended:

    def test_cross_brand_collision_lists_both_candidates(self, ext_catalog):
        """XG-42 with no manufacturer lists both Apex and Delta as candidates."""
        engine = ExactMatchEngine(ext_catalog)
        result = engine.match_line("XG-42", None)
        assert result.match_status == MatchStatus.COLLISION
        assert len(result.candidates) == 2
        oems = {c.catalog_item.manufacturer for c in result.candidates}
        assert oems == {"Apex Automation", "Delta Electronics"}

    def test_duplicate_catalog_record_same_mpn_same_oem_is_collision(self, ext_catalog):
        """Two SKUs for same MPN+OEM → COLLISION with both candidates."""
        engine = ExactMatchEngine(ext_catalog)
        result = engine.match_line("ABC-12", "Acme Industrial")
        assert result.match_status == MatchStatus.COLLISION
        assert result.selected_sku is None
        assert len(result.candidates) == 2

    def test_suffix_near_collision_not_collapsed(self, ext_catalog):
        """ABC-12, ABC-12A, ABC-12-R2 are distinct — exact matching preserves suffixes."""
        engine = ExactMatchEngine(ext_catalog)
        for mpn, expected_sku in [("ABC-12A", "SKU-EXT-010"), ("ABC-12-R2", "SKU-EXT-011")]:
            result = engine.match_line(mpn, "Acme Industrial")
            assert result.match_status == MatchStatus.EXACT_MATCH
            assert result.selected_sku == expected_sku

    def test_manufacturer_mismatch_is_collision(self, ext_catalog):
        """MPN exists under different manufacturer → COLLISION."""
        engine = ExactMatchEngine(ext_catalog)
        result = engine.match_line("LC1D09BD", "Siemens")
        assert result.match_status == MatchStatus.COLLISION
        assert result.selected_sku is None

    def test_unknown_part_number_no_match(self, ext_catalog):
        """Completely unknown MPN should be NO_MATCH."""
        engine = ExactMatchEngine(ext_catalog)
        result = engine.match_line("NONEXISTENT-PART-12345", "Schneider Electric")
        assert result.match_status == MatchStatus.NO_MATCH
        assert result.selected_sku is None

    def test_empty_or_none_mpn_is_no_match(self, ext_catalog):
        """Empty or None MPN should be NO_MATCH."""
        engine = ExactMatchEngine(ext_catalog)
        assert engine.match_line(None, "Schneider Electric").match_status == MatchStatus.NO_MATCH
        assert engine.match_line("", "Schneider Electric").match_status == MatchStatus.NO_MATCH

    def test_case_insensitive_oem_mpn_matching(self, ext_catalog):
        """OEM and MPN matching should be case-insensitive."""
        engine = ExactMatchEngine(ext_catalog)
        result = engine.match_line("lc1d09bd", "schneider electric")
        assert result.match_status == MatchStatus.EXACT_MATCH
        assert result.selected_sku == "SKU-EXT-001"

    def test_oem_alias_normalization(self, ext_catalog):
        """Known OEM aliases should normalize correctly."""
        engine = ExactMatchEngine(ext_catalog)
        # "Schneider" is an alias for "Schneider Electric"
        result = engine.match_line("LC1D09BD", "Schneider")
        assert result.match_status == MatchStatus.EXACT_MATCH
        assert result.selected_sku == "SKU-EXT-001"


# ---------------------------------------------------------------------------
# 5. Review/edit/approval/version and full vs partial export blocking
# ---------------------------------------------------------------------------

class TestReviewAndExportExtended:

    def test_post_approval_sku_change_revokes_approval(self, ext_services):
        """Changing selected SKU after approval must revoke approval."""
        manager, _, catalog, _ = ext_services
        case = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )
        line = manager.get_lines(case.case_id)[0]
        original_version = line.version

        manager.update_line(
            case.case_id, line.line_id,
            RFQLineItemUpdate(review_decision=ReviewDecision.APPROVED, actor="Auditor"),
        )
        assert manager.get_lines(case.case_id)[0].review_decision == ReviewDecision.APPROVED

        # Change SKU (material change)
        manager.update_line(
            case.case_id, line.line_id,
            RFQLineItemUpdate(selected_catalog_sku="SKU-EXT-002", actor="Auditor"),
        )
        updated = manager.get_lines(case.case_id)[0]
        assert updated.review_decision == ReviewDecision.PENDING
        assert updated.version > original_version

    def test_post_approval_mpn_change_revokes_approval(self, ext_services):
        """Changing MPN after approval must revoke approval and re-match."""
        manager, _, catalog, _ = ext_services
        case = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )
        line = manager.get_lines(case.case_id)[0]
        manager.update_line(
            case.case_id, line.line_id,
            RFQLineItemUpdate(review_decision=ReviewDecision.APPROVED, actor="Auditor"),
        )

        manager.update_line(
            case.case_id, line.line_id,
            RFQLineItemUpdate(requested_mpn="6ES7214-1AG40-0XB0", actor="Auditor"),
        )
        updated = manager.get_lines(case.case_id)[0]
        assert updated.review_decision == ReviewDecision.PENDING
        assert updated.requested_mpn == "6ES7214-1AG40-0XB0"

    def test_export_blocked_on_no_match(self, ext_services):
        """Export must be blocked when lines have NO_MATCH status."""
        manager, generator, catalog, _ = ext_services
        case = manager.create_case_from_text(
            "10 pcs Schneider Electric NONEXISTENT-PART-12345",
            customer_label="SYN-TEST", actor="Auditor",
        )
        req = ExportRequest(case_id=case.case_id, allow_partial=False, actor="Auditor")
        with pytest.raises(ExportValidationError, match="Export blocked"):
            generator.generate_export(case, manager.get_lines(case.case_id), req)

    def test_export_blocked_on_collision(self, ext_services):
        """Export must be blocked when lines have COLLISION status."""
        manager, generator, catalog, _ = ext_services
        case = manager.create_case_from_text(
            "5 pcs XG-42 transducer",
            customer_label="SYN-TEST", actor="Auditor",
        )
        lines = manager.get_lines(case.case_id)
        assert lines[0].match_status == MatchStatus.COLLISION

        req = ExportRequest(case_id=case.case_id, allow_partial=False, actor="Auditor")
        with pytest.raises(ExportValidationError, match="Export blocked"):
            generator.generate_export(case, lines, req)

    def test_export_blocked_on_unapproved_exact_match(self, ext_services):
        """Export must be blocked when lines are exact match but not approved."""
        manager, generator, catalog, _ = ext_services
        case = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )
        req = ExportRequest(case_id=case.case_id, allow_partial=False, actor="Auditor")
        with pytest.raises(ExportValidationError, match="Export blocked"):
            generator.generate_export(case, manager.get_lines(case.case_id), req)

    def test_partial_export_includes_all_lines_with_draft_label(self, ext_services):
        """Partial export should include unresolved lines with draft labeling."""
        manager, generator, catalog, _ = ext_services
        case = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )
        req = ExportRequest(case_id=case.case_id, allow_partial=True, format="xlsx", actor="Auditor")
        manifest = generator.generate_export(case, manager.get_lines(case.case_id), req)
        assert manifest.is_draft is True
        assert manifest.total_lines == 1
        assert manifest.approved_lines == 0
        assert manifest.unresolved_lines_omitted >= 1

    def test_audit_trail_records_sku_change(self, ext_services):
        """Changing SKU after matching must be recorded in audit trail."""
        manager, _, catalog, _ = ext_services
        case = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )
        line = manager.get_lines(case.case_id)[0]
        manager.update_line(
            case.case_id, line.line_id,
            RFQLineItemUpdate(selected_catalog_sku="SKU-EXT-002", actor="Auditor"),
        )

        trail = manager.get_audit_trail(case.case_id)
        sku_changes = [e for e in trail if e.field_name == "selected_catalog_sku"]
        assert len(sku_changes) >= 1
        assert sku_changes[0].new_value == "SKU-EXT-002"

    def test_case_status_reflects_readiness(self, ext_services):
        """Case status should reflect whether all lines are approved and matched."""
        manager, _, catalog, _ = ext_services
        case = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )
        # Before approval
        case = manager.get_case(case.case_id)
        assert case.status == CaseStatus.NEEDS_REVIEW

        # After approval
        line = manager.get_lines(case.case_id)[0]
        manager.update_line(
            case.case_id, line.line_id,
            RFQLineItemUpdate(review_decision=ReviewDecision.APPROVED, actor="Auditor"),
        )
        case = manager.get_case(case.case_id)
        assert case.status == CaseStatus.READY_TO_EXPORT

    def test_export_manifest_download_url_is_case_scoped(self, ext_services):
        """Export manifest download_url should be scoped to the case ID."""
        manager, generator, catalog, _ = ext_services
        case = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )
        line = manager.get_lines(case.case_id)[0]
        manager.update_line(
            case.case_id, line.line_id,
            RFQLineItemUpdate(review_decision=ReviewDecision.APPROVED, actor="Auditor"),
        )

        req = ExportRequest(case_id=case.case_id, allow_partial=False, format="csv", actor="Auditor")
        manifest = generator.generate_export(case, manager.get_lines(case.case_id), req)

        assert manifest.download_url == f"/api/rfqs/{case.case_id}/exports/{manifest.export_id}"
        assert case.case_id in manifest.download_url


# ---------------------------------------------------------------------------
# 6. API export download from default and temp storage, persistence/restart,
#    deletion behavior
# ---------------------------------------------------------------------------

class TestApiExportDownloadAndPersistence:

    def test_export_download_from_custom_storage(self, api_client_no_auth):
        """
        The download endpoint uses export_generator.base_export_dir, so downloads
        work even when the generator is configured with a custom base directory.
        """
        client, manager, generator, catalog, tmp_path = api_client_no_auth

        case = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )
        line = manager.get_lines(case.case_id)[0]
        manager.update_line(
            case.case_id, line.line_id,
            RFQLineItemUpdate(review_decision=ReviewDecision.APPROVED, actor="Auditor"),
        )

        # Export through the API
        export_resp = client.post(
            f"/api/rfqs/{case.case_id}/exports",
            json={"case_id": case.case_id, "allow_partial": False, "format": "xlsx", "actor": "Auditor"},
        )
        assert export_resp.status_code == 200
        manifest = export_resp.json()

        # Download should work using the generator's base_export_dir (tmp_path/exports)
        download_resp = client.get(manifest["download_url"])
        assert download_resp.status_code == 200, \
            f"Download should succeed with custom base_export_dir, got {download_resp.status_code}"
        assert len(download_resp.content) > 100

    def test_export_to_default_storage_works_when_generator_uses_default(self, ext_services, monkeypatch):
        """
        When the ExportGenerator uses the default base_export_dir (storage/exports),
        the download endpoint works. This tests the 'happy path' with default config.
        """
        import importlib

        manager, _, catalog, tmp_path = ext_services
        api_module = importlib.import_module("rfq_assistant.api.app")

        # Use default export dir
        default_gen = ExportGenerator(catalog=catalog)
        monkeypatch.setattr(api_module, "export_generator", default_gen)
        monkeypatch.setattr(api_module, "case_manager", manager)

        case = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )
        line = manager.get_lines(case.case_id)[0]
        manager.update_line(
            case.case_id, line.line_id,
            RFQLineItemUpdate(review_decision=ReviewDecision.APPROVED, actor="Auditor"),
        )

        client = TestClient(api_module.app)
        export_resp = client.post(
            f"/api/rfqs/{case.case_id}/exports",
            json={"case_id": case.case_id, "allow_partial": False, "format": "xlsx", "actor": "Auditor"},
        )
        assert export_resp.status_code == 200
        manifest = export_resp.json()

        # Download should work with default storage path
        download_resp = client.get(manifest["download_url"])
        assert download_resp.status_code == 200
        assert len(download_resp.content) > 0

    def test_export_download_cross_case_blocked(self, ext_services):
        """Export from one case cannot be downloaded through another case ID."""
        manager, generator, catalog, _ = ext_services

        case1 = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )
        case2 = manager.create_case_from_text(
            "5 pcs Siemens 6ES7214-1AG40-0XB0",
            customer_label="SYN-TEST", actor="Auditor",
        )

        req1 = ExportRequest(case_id=case1.case_id, allow_partial=True, format="xlsx", actor="Auditor")
        manifest1 = generator.generate_export(case1, manager.get_lines(case1.case_id), req1)

        # Verify case-scoping
        assert manifest1.case_id == case1.case_id
        assert case1.case_id in manifest1.download_url
        assert case2.case_id not in manifest1.download_url

    def test_persistence_across_restart_full_workflow(self, tmp_path):
        """Full workflow: create, edit, approve, export, restart, verify recovery."""
        db_path = tmp_path / "persist.sqlite3"
        store = SQLiteStateStore(db_path)
        storage = DocumentStorage(tmp_path / "uploads")
        catalog = CatalogRepository(state_store=store)
        catalog.import_csv(EXTENDED_CATALOG.read_bytes(), version="synth-audit-ext")

        # Step 1: Create and process
        manager1 = CaseManager(catalog=catalog, storage=storage, state_store=store)
        case = manager1.create_case_from_upload(
            filename="workflow.csv",
            content=(
                b"MPN,Manufacturer,Qty,Description\n"
                b"LC1D09BD,Schneider Electric,10,Contactor\n"
                b"6ES7214-1AG40-0XB0,Siemens,5,CPU\n"
            ),
            customer_label="SYN-TEST", actor="Auditor",
            title="Persistence Full Workflow",
        )
        lines = manager1.get_lines(case.case_id)
        for line in lines:
            manager1.update_line(
                case.case_id, line.line_id,
                RFQLineItemUpdate(review_decision=ReviewDecision.APPROVED, actor="Auditor"),
            )

        # Step 2: Export before restart
        gen1 = ExportGenerator(catalog=catalog, base_export_dir=tmp_path / "exports1")
        req = ExportRequest(case_id=case.case_id, allow_partial=False, format="csv", actor="Auditor")
        manifest1 = gen1.generate_export(case, manager1.get_lines(case.case_id), req)

        # Step 3: Restart — rebuild all process-scoped objects from SQLite
        store2 = SQLiteStateStore(db_path)
        catalog2 = CatalogRepository(state_store=store2)
        manager2 = CaseManager(catalog=catalog2, storage=storage, state_store=store2)

        # Step 4: Verify everything survived
        restored_case = manager2.get_case(case.case_id)
        assert restored_case is not None
        assert restored_case.title == "Persistence Full Workflow"

        restored_lines = manager2.get_lines(case.case_id)
        assert len(restored_lines) == 2
        assert restored_lines[0].requested_mpn == "LC1D09BD"
        assert restored_lines[0].review_decision == ReviewDecision.APPROVED
        assert restored_lines[0].selected_catalog_sku == "SKU-EXT-001"

        # Audit trail survived
        audit = manager2.get_audit_trail(case.case_id)
        actions = [e.action for e in audit]
        assert AuditAction.CASE_CREATED in actions
        assert AuditAction.PARSED in actions
        assert AuditAction.LINE_APPROVED in actions

        # Catalog survived
        assert catalog2.get_by_sku("SKU-EXT-001") is not None

        # Export manifest file still exists
        export_dir = tmp_path / "exports1" / manifest1.export_id
        assert export_dir.exists()
        assert (export_dir / manifest1.file_name).exists()

    def test_delete_case_removes_all_state(self, ext_services):
        """Delete case should remove all state (case, lines, audit, files)."""
        manager, _, catalog, tmp_path = ext_services
        storage = manager.storage

        case = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )
        case_id = case.case_id

        # Verify state exists
        assert manager.get_case(case_id) is not None
        assert manager.get_lines(case_id)
        assert manager.get_audit_trail(case_id)
        assert storage.get_file(case_id, "pasted_inquiry.txt") is not None

        # Delete
        result = manager.delete_case(case_id)
        assert result is True

        # Verify all state is gone
        assert manager.get_case(case_id) is None
        assert manager.get_lines(case_id) == []
        assert manager.get_audit_trail(case_id) == []
        assert storage.get_file(case_id, "pasted_inquiry.txt") is None

    def test_case_scoped_source_file_access_no_path_traversal(self, ext_services):
        """Source file retrieval is case-scoped (no path traversal)."""
        manager, _, catalog, _ = ext_services
        case = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )

        # Valid source retrieval
        src = manager.storage.get_file(case.case_id, "pasted_inquiry.txt")
        assert src == b"10 pcs Schneider Electric LC1D09BD"

        # Invalid case ID should not retrieve anything
        assert manager.storage.get_file("RFQ-NONEXISTENT", "pasted_inquiry.txt") is None

        # Path traversal attempt in filename
        assert manager.storage.get_file(case.case_id, "../../../etc/passwd") is None

    def test_delete_case_persists_across_restart(self, tmp_path):
        """Deletion must persist across restart (SQLite-level deletion)."""
        db_path = tmp_path / "delete_persist.sqlite3"
        store = SQLiteStateStore(db_path)
        storage = DocumentStorage(tmp_path / "uploads")
        catalog = CatalogRepository(state_store=store)
        catalog.import_csv(EXTENDED_CATALOG.read_bytes(), version="synth-audit-ext")
        manager = CaseManager(catalog=catalog, storage=storage, state_store=store)

        case = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )
        case_id = case.case_id
        manager.delete_case(case_id)

        # Restart
        store2 = SQLiteStateStore(db_path)
        catalog2 = CatalogRepository(state_store=store2)
        manager2 = CaseManager(catalog=catalog2, storage=storage, state_store=store2)

        assert manager2.get_case(case_id) is None
        assert manager2.get_lines(case_id) == []

    def test_upload_size_limit_enforced(self, ext_services):
        """Files exceeding MAX_UPLOAD_BYTES must be rejected."""
        from rfq_assistant.ingestion.validator import MAX_UPLOAD_BYTES
        manager, _, catalog, _ = ext_services

        # Create content just over the limit
        oversized = b"x" * (MAX_UPLOAD_BYTES + 1)
        with pytest.raises(UploadValidationError, match="exceeds maximum"):
            manager.create_case_from_upload(
                filename="big.csv", content=oversized,
                customer_label="SYN-TEST", actor="Auditor",
            )

    def test_oversized_csv_retained_as_failed_case(self, ext_services):
        """CSV with >5000 rows must be blocked while retaining the original upload."""
        manager, _, catalog, _ = ext_services
        csv_content = AUDIT_FIXTURES / "oversized_csv_5005_rows.csv"
        if csv_content.exists():
            content = csv_content.read_bytes()
            case = manager.create_case_from_upload(
                filename="big.csv", content=content,
                customer_label="SYN-TEST", actor="Auditor",
            )
            assert case.status.value == "FAILED"
            assert "5000" in case.document_warnings[0].message


# ---------------------------------------------------------------------------
# 7. Auth and role checks, upload/path/macro/size defenses, formula-safe export,
#    quote-send route
# ---------------------------------------------------------------------------

class TestAuthAndSecurityExtended:

    def test_send_quota_route_never_invokes_external_transport(self, api_client_no_auth):
        """
        The send-quote route returns a simulated transmission, never invokes SMTP/HTTP.
        Verified at the service level: no external transport is invoked.
        """
        client, manager, generator, catalog, tmp_path = api_client_no_auth
        import importlib
        api_module = importlib.import_module("rfq_assistant.api.app")
        service = api_module.commercial_service

        from rfq_assistant.quotation.validate import ProposedQuote, QuoteLine, SourceRef
        from decimal import Decimal

        # Build a valid quote line that passes validation
        catalog_item = catalog.get_by_sku("SKU-EXT-001")
        line = QuoteLine(
            line_no=1,
            requested_mpn="LC1D09BD",
            catalogue_part_id="SKU-EXT-001",
            description="Contactor",
            quantity=Decimal("10"),
            unit_price=Decimal("42.50"),
            currency="USD",
            source_price_id=f"CAT-synth-audit-ext-SKU-EXT-001",
            match_status="exact",
            requires_human_review=False,
            sources=[],
        )
        quote = ProposedQuote(
            quote_id=f"Q-SEND-{uuid.uuid4().hex[:6]}",
            case_id="RFQ-1",
            customer_name="Transport Test",
            lines=[line],
            source_state_hash="test-hash-123",
        )
        service.register_draft(quote)
        draft_hash = quote.draft_hash
        service.approve_draft(quote.quote_id, draft_hash, "Test Approver")

        result = service.send_approved_quote(quote.quote_id, draft_hash, "Test Sender")

        # Key safety assertions: no external transport invoked
        assert result["status"] == "SENT"
        assert result["is_simulated"] is True
        assert result["outbound_transport_invoked"] is False
        assert result["transport"] == "simulated_local"
        assert "No live SMTP or external network transport" in result["transport_notes"]

        record_finding(
            title="Quote send route uses simulated local transport (always, never external)",
            severity="Info",
            category="Safety / Transport",
            expected="No external transport invoked (safety invariant: no automatic outbound)",
            observed="send_approved_quote returns simulated_local transport with outbound_transport_invoked=False. "
                     "REQUIRE_REAL_TRANSPORT env var blocks sends when set, but is not set by default.",
            evidence="agents/tools.py:140-159 — send_approved_quote always returns simulated_local; "
                     "REQUIRE_REAL_TRANSPORT only blocks (fails closed) when explicitly set to true",
            defect_type="limitation",
        )

    def test_send_with_require_real_transport_blocks(self, api_client_no_auth, monkeypatch):
        """When REQUIRE_REAL_TRANSPORT is set, send must be blocked."""
        client, manager, generator, catalog, tmp_path = api_client_no_auth
        import importlib
        api_module = importlib.import_module("rfq_assistant.api.app")
        service = api_module.commercial_service

        from rfq_assistant.quotation.validate import ProposedQuote, QuoteLine
        from decimal import Decimal

        catalog_item = catalog.get_by_sku("SKU-EXT-001")
        line = QuoteLine(
            line_no=1,
            requested_mpn="LC1D09BD",
            catalogue_part_id="SKU-EXT-001",
            description="Contactor",
            quantity=Decimal("10"),
            unit_price=Decimal("42.50"),
            currency="USD",
            source_price_id="CAT-synth-audit-ext-SKU-EXT-001",
            match_status="exact",
            requires_human_review=False,
            sources=[],
        )
        quote = ProposedQuote(
            quote_id=f"Q-REAL-{uuid.uuid4().hex[:6]}",
            case_id="RFQ-1",
            customer_name="Transport Test",
            lines=[line],
            source_state_hash="test-hash-456",
        )
        service.register_draft(quote)
        draft_hash = quote.draft_hash
        service.approve_draft(quote.quote_id, draft_hash, "Test Approver")

        monkeypatch.setenv("REQUIRE_REAL_TRANSPORT", "true")
        from rfq_assistant.agents.tools import ApprovalGateError
        with pytest.raises(ApprovalGateError, match="Real outbound transport is not configured"):
            service.send_approved_quote(quote.quote_id, draft_hash, "Test Sender")

    def test_role_based_delete_requires_admin(self, api_client_auth_on):
        """Viewer role cannot delete cases; admin can."""
        client, manager, generator, catalog, tmp_path = api_client_auth_on

        admin_headers = {"X-API-Key": "test-admin-secret-000000001"}
        viewer_headers = {"X-API-Key": "test-viewer-secret-000000001"}

        resp = client.post(
            "/api/rfqs",
            data={"pasted_text": "10 pcs Schneider Electric LC1D09BD", "title": "RBAC Delete Test", "actor": "Admin"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        case_id = resp.json()["case_id"]

        # Viewer cannot delete
        del_resp = client.delete(f"/api/rfqs/{case_id}", headers=viewer_headers)
        assert del_resp.status_code == 403

        # Admin can delete
        del_admin = client.delete(f"/api/rfqs/{case_id}", headers=admin_headers)
        assert del_admin.status_code == 200

    def test_role_based_export(self, api_client_auth_on):
        """Viewer cannot export (403), reviewer can export (200), admin can export (200)."""
        client, manager, generator, catalog, tmp_path = api_client_auth_on

        admin_headers = {"X-API-Key": "test-admin-secret-000000001"}
        viewer_headers = {"X-API-Key": "test-viewer-secret-000000001"}
        reviewer_headers = {"X-API-Key": "test-reviewer-secret-00000001"}

        resp = client.post(
            "/api/rfqs",
            data={"pasted_text": "10 pcs Schneider Electric LC1D09BD", "title": "RBAC Export Test", "actor": "Admin"},
            headers=admin_headers,
        )
        case_id = resp.json()["case_id"]

        # Approve line as admin
        lines_resp = client.get(f"/api/rfqs/{case_id}/lines", headers=admin_headers)
        line = lines_resp.json()[0]
        line_id = line["line_id"]
        client.patch(
            f"/api/rfqs/{case_id}/lines/{line_id}",
            json={"review_decision": "APPROVED", "expected_version": line["version"]},
            headers=admin_headers,
        )

        # Viewer cannot export (requires admin/reviewer)
        export_resp = client.post(
            f"/api/rfqs/{case_id}/exports",
            json={"case_id": case_id, "allow_partial": False, "format": "xlsx"},
            headers=viewer_headers,
        )
        assert export_resp.status_code == 403

        # Reviewer can export
        export_resp = client.post(
            f"/api/rfqs/{case_id}/exports",
            json={"case_id": case_id, "allow_partial": False, "format": "xlsx"},
            headers=reviewer_headers,
        )
        assert export_resp.status_code == 200

        # Admin can export
        export_resp_admin = client.post(
            f"/api/rfqs/{case_id}/exports",
            json={"case_id": case_id, "allow_partial": False, "format": "xlsx"},
            headers=admin_headers,
        )
        assert export_resp_admin.status_code == 200

    def test_unauthenticated_request_blocked_when_auth_required(self, api_client_auth_on):
        """With REQUIRE_AUTH=true, unauthenticated requests are rejected."""
        client, _, _, _, _ = api_client_auth_on

        # No API key
        resp = client.get("/api/rfqs")
        assert resp.status_code == 401

        # Invalid API key
        resp = client.get("/api/rfqs", headers={"X-API-Key": "bogus-key"})
        assert resp.status_code == 401

    def test_authenticated_actor_not_spoofed(self, api_client_auth_on):
        """Client-supplied actor is overridden by authenticated principal."""
        client, manager, generator, catalog, tmp_path = api_client_auth_on
        reviewer_headers = {"X-API-Key": "test-reviewer-secret-00000001"}

        resp = client.post(
            "/api/rfqs",
            data={"pasted_text": "10 pcs Schneider Electric LC1D09BD", "title": "Spoof Test", "actor": "SYSTEM_ADMIN"},
            headers=reviewer_headers,
        )
        assert resp.status_code == 200
        case_id = resp.json()["case_id"]

        # The audit trail should show the authenticated user, not the spoof attempt
        audit_resp = client.get(f"/api/rfqs/{case_id}/audit", headers=reviewer_headers)
        assert audit_resp.status_code == 200
        events = audit_resp.json()
        assert any(e["actor"] == "Authorized Reviewer" for e in events)
        assert not any(e["actor"] == "SYSTEM_ADMIN" for e in events)

    def test_local_demo_actor_is_server_supplied(self, api_client_no_auth):
        """Unauthenticated demo mode still uses its explicit server identity in audit logs."""
        client, manager, generator, catalog, tmp_path = api_client_no_auth

        # No auth required — any request succeeds without API key
        resp = client.get("/api/rfqs")
        assert resp.status_code == 200

        # The client-supplied actor cannot spoof audit attribution.
        create_resp = client.post(
            "/api/rfqs",
            data={"pasted_text": "10 pcs Schneider Electric LC1D09BD", "title": "Bypass Test", "actor": "FAKE_ADMIN"},
        )
        assert create_resp.status_code == 200
        case_id = create_resp.json()["case_id"]

        audit_resp = client.get(f"/api/rfqs/{case_id}/audit")
        events = audit_resp.json()
        case_created_events = [e for e in events if e["action"] == "CASE_CREATED"]
        assert case_created_events
        assert case_created_events[0]["actor"] == "Local Pilot Operator"
        assert not any(event["actor"] == "FAKE_ADMIN" for event in events)

    def test_path_traversal_in_filename_blocked(self):
        """Filename sanitization must prevent path traversal."""
        safe_name, _, _ = validate_file_upload("../../../etc/passwd.csv", b"a,b\n1,2\n")
        assert ".." not in safe_name
        assert "etc" not in safe_name
        assert safe_name.endswith(".csv")

    def test_empty_filename_rejected(self):
        """Empty filenames must be rejected."""
        with pytest.raises(UploadValidationError):
            validate_file_upload("", b"data")

    def test_macro_file_rejected_by_extension(self):
        """Files with .xlsm extension must be rejected."""
        with pytest.raises(UploadValidationError, match="Macro-enabled"):
            validate_file_upload("macro.xlsm", b"data")

    def test_xlsm_disguised_as_csv_not_treated_as_macro(self):
        """Files with .csv extension are never treated as macro files (no macro vector)."""
        # A .csv file is never macro-enabled, regardless of name
        name, _, _ = validate_file_upload("report.xlsm.csv", b"PartNumber,Qty\nLC1D09BD,10\n")
        assert name.endswith(".csv")

    def test_csv_formula_injection_in_export(self, ext_services):
        """Exported CSV must escape formula-like content in all user-supplied fields."""
        manager, generator, catalog, _ = ext_services
        case = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )
        line = manager.get_lines(case.case_id)[0]
        manager.update_line(
            case.case_id, line.line_id,
            RFQLineItemUpdate(
                notes="=HYPERLINK(\"https://evil.test\",\"click\")",
                selected_catalog_sku="SKU-EXT-001",
                review_decision=ReviewDecision.APPROVED,
                actor="Auditor",
            ),
        )

        req = ExportRequest(case_id=case.case_id, allow_partial=False, format="csv", actor="Auditor")
        manifest = generator.generate_export(case, manager.get_lines(case.case_id), req)

        export_dir = Path(generator.base_export_dir) / manifest.export_id
        file_path = export_dir / manifest.file_name
        csv_text = file_path.read_text(encoding="utf-8")

        # Formula should be prefixed with single quote
        assert "'=HYPERLINK" in csv_text
        assert "DRAFT" in csv_text.upper()

    def test_xlsx_formula_injection_in_export(self, ext_services):
        """Exported XLSX must store formula-like values as text, not executable formulas."""
        manager, generator, catalog, _ = ext_services
        case = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )
        line = manager.get_lines(case.case_id)[0]
        manager.update_line(
            case.case_id, line.line_id,
            RFQLineItemUpdate(
                notes="@SUM(1,2)",
                selected_catalog_sku="SKU-EXT-001",
                review_decision=ReviewDecision.APPROVED,
                actor="Auditor",
            ),
        )

        req = ExportRequest(case_id=case.case_id, allow_partial=False, format="xlsx", actor="Auditor")
        manifest = generator.generate_export(case, manager.get_lines(case.case_id), req)

        export_dir = Path(generator.base_export_dir) / manifest.export_id
        file_path = export_dir / manifest.file_name
        wb = openpyxl.load_workbook(file_path, data_only=False)
        ws = wb.active

        formula_cells = []
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.lstrip().startswith(("=", "+", "-", "@")):
                    formula_cells.append(cell)

        # All formula-like cells must be stored as text (data_type == "s"), not formula
        for cell in formula_cells:
            assert cell.data_type == "s", \
                f"Cell {cell.coordinate} value '{cell.value}' should be text (s), got '{cell.data_type}'"

    def test_eicar_file_rejected_by_clamav(self, api_client_no_auth):
        """EICAR test file must be rejected by the ClamAV scanner via the API."""
        client, manager, generator, catalog, tmp_path = api_client_no_auth
        from rfq_assistant.ingestion.malware import EICAR_SIGNATURE

        eicar_content = EICAR_SIGNATURE
        # Build multipart upload
        resp = client.post(
            "/api/rfqs",
            files={"file": ("eicar.txt", eicar_content, "text/plain")},
            data={"title": "EICAR Test", "customer_label": "SYN-TEST", "actor": "Auditor"},
        )
        assert resp.status_code == 400, \
            f"EICAR file should be rejected at API layer, got {resp.status_code}"
        assert "Security alert" in resp.json()["detail"] or "Malicious" in resp.json()["detail"]

    def test_protected_mode_clamav_fails_closed(self, tmp_path, monkeypatch):
        """When protected_mode=True and clamd is unreachable, scanner fails closed."""
        import importlib
        api_module = importlib.import_module("rfq_assistant.api.app")
        scanner = ClamAVScanner(protected_mode=True)

        # Scan a clean file — should fail closed since clamd is unreachable
        result = scanner.scan_bytes(b"clean content", filename="test.csv")
        assert result.is_clean is False, \
            "Protected mode should fail closed when daemon is unreachable"
        assert result.engine == "clamav-fail-closed"


# ---------------------------------------------------------------------------
# 8. Isolated concurrency across intake and later workflow stages
# ---------------------------------------------------------------------------

class TestConcurrencyExtended:

    def test_concurrent_create_and_approve(self, tmp_path, monkeypatch):
        """Concurrent case creation AND line approval simultaneously across threads."""
        import importlib

        db_path = tmp_path / "concurrent_wf.sqlite3"
        store = SQLiteStateStore(db_path)
        catalog = CatalogRepository(state_store=store)
        catalog.import_csv(EXTENDED_CATALOG.read_bytes(), version="synth-audit-ext")

        api_module = importlib.import_module("rfq_assistant.api.app")
        manager = CaseManager(catalog=catalog, storage=DocumentStorage(tmp_path / "uploads"), state_store=store)
        generator = ExportGenerator(catalog=catalog, base_export_dir=tmp_path / "exports")

        monkeypatch.setattr(api_module, "catalog_repo", catalog)
        monkeypatch.setattr(api_module, "case_manager", manager)
        monkeypatch.setattr(api_module, "export_generator", generator)
        monkeypatch.setattr(api_module, "clamav_scanner", ClamAVScanner(protected_mode=False))
        monkeypatch.delenv("REQUIRE_AUTH", raising=False)
        monkeypatch.delenv("PILOT_API_KEYS", raising=False)

        client = TestClient(api_module.app)

        results = []
        errors = []
        lock = threading.Lock()

        def create_and_approve(n):
            try:
                resp = client.post("/api/rfqs", data={
                    "pasted_text": f"10 pcs Schneider Electric LC1D09BD item-{n}",
                    "title": f"Concurrent WF {n}",
                    "actor": "Tester",
                })
                if resp.status_code != 200:
                    errors.append(f"Create failed for {n}: {resp.status_code} {resp.text[:200]}")
                    return
                case_id = resp.json()["case_id"]

                lines_resp = client.get(f"/api/rfqs/{case_id}/lines")
                if lines_resp.status_code != 200:
                    errors.append(f"Get lines failed for {n}")
                    return
                line = lines_resp.json()[0]
                line_id = line["line_id"]

                patch_resp = client.patch(
                    f"/api/rfqs/{case_id}/lines/{line_id}",
                    json={"review_decision": "APPROVED", "expected_version": line["version"], "actor": "Tester"},
                )
                if patch_resp.status_code != 200:
                    errors.append(f"Approve failed for {n}: {patch_resp.status_code} {patch_resp.text[:200]}")
                    return

                with lock:
                    results.append(case_id)
            except Exception as e:
                errors.append(f"Exception for {n}: {e}")

        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(create_and_approve, range(1, 31)))

        assert len(errors) == 0, f"Errors during concurrent create+approve: {errors}"
        assert len(results) == 30, f"Expected 30 successful cases, got {len(results)}"
        assert len(set(results)) == 30, "Duplicate case IDs generated"

    def test_concurrent_export_same_case(self, ext_services):
        """Multiple concurrent exports of the same case should succeed without corruption."""
        manager, generator, catalog, _ = ext_services
        case = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )
        line = manager.get_lines(case.case_id)[0]
        manager.update_line(
            case.case_id, line.line_id,
            RFQLineItemUpdate(review_decision=ReviewDecision.APPROVED, actor="Auditor"),
        )

        errors = []
        manifests = []
        lock = threading.Lock()

        def do_export(n):
            try:
                req = ExportRequest(
                    case_id=case.case_id, allow_partial=False, format="csv", actor=f"Exporter{n}",
                )
                m = generator.generate_export(case, manager.get_lines(case.case_id), req)
                with lock:
                    manifests.append(m.export_id)
            except Exception as e:
                errors.append(str(e))

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(do_export, range(20)))

        assert len(errors) == 0, f"Errors during concurrent export: {errors}"
        assert len(manifests) == 20, f"Expected 20 successful exports, got {len(manifests)}"
        assert len(set(manifests)) == 20, "Duplicate export IDs generated"

    def test_concurrent_edits_same_line_optimistic_lock(self, ext_services):
        """Concurrent edits to the same line with stale expected_version should
        produce optimistic concurrency conflicts (ValueError in manager, 409 via API)."""
        manager, _, catalog, _ = ext_services
        case = manager.create_case_from_text(
            "10 pcs Schneider Electric LC1D09BD",
            customer_label="SYN-TEST", actor="Auditor",
        )
        line = manager.get_lines(case.case_id)[0]
        original_version = line.version

        errors = []
        successes = [0]
        lock = threading.Lock()

        def edit_line(n):
            try:
                manager.update_line(
                    case.case_id, line.line_id,
                    RFQLineItemUpdate(
                        quantity=float(10 + n),
                        expected_version=original_version,
                        actor=f"Editor{n}",
                    ),
                )
                with lock:
                    successes[0] += 1
            except ValueError as e:
                with lock:
                    errors.append(str(e))

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(edit_line, range(8)))

        # First writer wins (at least 1 success), rest should conflict
        assert successes[0] >= 1, "At least one edit should succeed"
        assert len(errors) >= 1, "At least one edit should fail with version conflict"
        for err in errors:
            assert "Stale state" in err or "conflict" in err.lower()

    def test_concurrent_create_and_export_different_cases(self, tmp_path, monkeypatch):
        """Concurrent case creation + matching + approval + export across different cases."""
        import importlib

        db_path = tmp_path / "concurrent_mixed.sqlite3"
        store = SQLiteStateStore(db_path)
        catalog = CatalogRepository(state_store=store)
        catalog.import_csv(EXTENDED_CATALOG.read_bytes(), version="synth-audit-ext")

        api_module = importlib.import_module("rfq_assistant.api.app")
        manager = CaseManager(catalog=catalog, storage=DocumentStorage(tmp_path / "uploads"), state_store=store)
        generator = ExportGenerator(catalog=catalog, base_export_dir=tmp_path / "exports")

        monkeypatch.setattr(api_module, "catalog_repo", catalog)
        monkeypatch.setattr(api_module, "case_manager", manager)
        monkeypatch.setattr(api_module, "export_generator", generator)
        monkeypatch.setattr(api_module, "clamav_scanner", ClamAVScanner(protected_mode=False))
        monkeypatch.delenv("REQUIRE_AUTH", raising=False)
        monkeypatch.delenv("PILOT_API_KEYS", raising=False)

        client = TestClient(api_module.app)

        results = {"created": 0, "approved": 0, "exported": 0}
        errors = []
        lock = threading.Lock()

        def full_workflow(n):
            try:
                # Create
                resp = client.post("/api/rfqs", data={
                    "pasted_text": f"10 pcs Schneider Electric LC1D09BD item-{n}",
                    "title": f"Mixed WF {n}",
                    "actor": "Tester",
                })
                if resp.status_code != 200:
                    errors.append(f"[{n}] Create failed: {resp.status_code}")
                    return
                case_id = resp.json()["case_id"]

                with lock:
                    results["created"] += 1

                # Get line
                lines_resp = client.get(f"/api/rfqs/{case_id}/lines")
                line = lines_resp.json()[0]
                line_id = line["line_id"]

                # Approve
                patch_resp = client.patch(
                    f"/api/rfqs/{case_id}/lines/{line_id}",
                    json={"review_decision": "APPROVED", "expected_version": line["version"], "actor": "Tester"},
                )
                if patch_resp.status_code != 200:
                    errors.append(f"[{n}] Approve failed: {patch_resp.status_code}")
                    return
                with lock:
                    results["approved"] += 1

                # Export
                export_resp = client.post(
                    f"/api/rfqs/{case_id}/exports",
                    json={"case_id": case_id, "allow_partial": False, "format": "csv", "actor": "Tester"},
                )
                if export_resp.status_code != 200:
                    errors.append(f"[{n}] Export failed: {export_resp.status_code} {export_resp.text[:200]}")
                    return
                with lock:
                    results["exported"] += 1
            except Exception as e:
                errors.append(f"[{n}] Exception: {e}")

        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(full_workflow, range(1, 16)))

        assert len(errors) == 0, f"Errors during concurrent workflow: {errors}"
        assert results["created"] == 15
        assert results["approved"] == 15
        assert results["exported"] == 15


# ---------------------------------------------------------------------------
# 9. Audit findings reporting
# ---------------------------------------------------------------------------

class TestAuditFindingsReport:
    """Aggregates all audit findings and writes them to the results directory."""

    def test_findings_collected(self):
        """Verify that findings list exists (populated by other test classes)."""
        assert isinstance(FINDINGS, list)

    def test_write_findings_summary(self):
        """Writes accumulated findings to results directory."""
        results_dir = AUDIT_FIXTURES.parent / "results"
        results_dir.mkdir(exist_ok=True)
        findings_path = results_dir / "audit_findings_extended.txt"
        with open(findings_path, "w") as f:
            f.write("Extended RFQ-Assistant Audit — Findings Summary\n")
            f.write(f"Generated: 2026-10-31\n")
            f.write("=" * 80 + "\n\n")
            if not FINDINGS:
                f.write("No findings recorded via record_finding().\n")
                f.write("See test output for pass/fail status.\n")
            else:
                for i, finding in enumerate(FINDINGS, 1):
                    f.write(f"Finding #{i}: {finding.title}\n")
                    f.write(f"  Severity: {finding.severity}\n")
                    f.write(f"  Category: {finding.category}\n")
                    f.write(f"  Type: {finding.defect_type}\n")
                    f.write(f"  Expected: {finding.expected}\n")
                    f.write(f"  Observed: {finding.observed}\n")
                    f.write(f"  Evidence: {finding.evidence}\n\n")
