"""Restart recovery checks for local durable RFQ state."""

import pytest

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion import DocumentParserError, DocumentStorage
from rfq_assistant.ingestion.parsers.spreadsheet_parser import SpreadsheetParser
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.persistence import SQLiteStateStore
from rfq_assistant.schemas.models import RFQLineItemUpdate


def test_case_line_audit_and_catalog_survive_manager_restart(tmp_path):
    database = tmp_path / "state" / "rfq.sqlite3"
    storage = DocumentStorage(tmp_path / "files")
    first_store = SQLiteStateStore(database)
    first_catalog = CatalogRepository(state_store=first_store)
    first_catalog.import_csv(
        b"internal_sku,manufacturer,manufacturer_part_number,description\n"
        b"SKU-1,Schneider Electric,LC1D09BD,Contactor\n"
    )
    first_manager = CaseManager(first_catalog, storage=storage, state_store=first_store)

    case = first_manager.create_case_from_upload(
        "request.csv",
        b"manufacturer,mpn,quantity,description\n"
        b"Schneider Electric,LC1D09BD,3,Contactor\n",
        title="Synthetic restart check",
    )
    assert len(case.source_coverage) == 1
    assert case.source_coverage[0].nonempty_regions == 2
    line = first_manager.get_lines(case.case_id)[0]
    assert line.field_provenance["requested_mpn"].origin.value == "DETERMINISTIC"
    assert line.field_provenance["requested_mpn"].source_locator.row_number == 2
    assert line.field_provenance["unit"].raw_value is None
    assert line.field_provenance["unit"].proposed_value == "EA"
    assert line.matched_catalog_version == "v1"
    edited = first_manager.update_line(
        case.case_id,
        line.line_id,
        RFQLineItemUpdate(quantity=5, actor="Reviewer A", expected_version=line.version),
    )
    assert edited.quantity == 5
    assert edited.field_provenance["quantity"].origin.value == "HUMAN"
    assert edited.field_provenance["quantity"].revision == 2
    assert edited.field_provenance["quantity"].raw_value == "3"

    # Recreate every process-scoped repository while retaining only SQLite and files.
    second_store = SQLiteStateStore(database)
    second_catalog = CatalogRepository(state_store=second_store)
    second_manager = CaseManager(second_catalog, storage=storage, state_store=second_store)

    restored_case = second_manager.get_case(case.case_id)
    restored_line = second_manager.get_lines(case.case_id)[0]
    assert restored_case is not None
    assert restored_case.title == "Synthetic restart check"
    assert restored_case.source_coverage == case.source_coverage
    assert restored_line.quantity == 5
    assert restored_line.version == edited.version
    assert restored_line.selected_catalog_sku == "SKU-1"
    assert restored_line.matched_catalog_version == "v1"
    assert restored_line.field_provenance == edited.field_provenance
    assert second_catalog.get_by_sku("SKU-1") is not None
    assert any(event.field_name == "quantity" for event in second_manager.get_audit_trail(case.case_id))
    assert storage.get_file(case.case_id, "request.csv") is not None


def test_provenance_does_not_guess_raw_quantity_from_row_text(tmp_path):
    from rfq_assistant.cases.manager import CaseManager
    from rfq_assistant.ingestion.parsers.base import ParsedLineDraft
    from rfq_assistant.schemas.models import SourceLocator

    draft = ParsedLineDraft(
        line_number=1,
        raw_text="LC1D09BD quantity 3",
        source_locator=SourceLocator(file_name="request.txt", text_snippet="LC1D09BD quantity 3"),
        requested_mpn="LC1D09BD",
        quantity=3,
    )

    provenance = CaseManager._build_field_provenance(draft)

    assert provenance["quantity"].proposed_value == "3.0"
    assert provenance["quantity"].raw_value is None


def test_delete_case_removes_durable_state_and_file(tmp_path):
    database = tmp_path / "state" / "rfq.sqlite3"
    storage = DocumentStorage(tmp_path / "files")
    store = SQLiteStateStore(database)
    manager = CaseManager(CatalogRepository(state_store=store), storage=storage, state_store=store)
    case = manager.create_case_from_upload("request.csv", b"MPN,Qty\nLC1D09BD,2\n")
    assert store.save_processing_artifact(
        case.case_id, "parsed_document", case.source_file.sha256_digest,
        "synthetic-profile", {"lines": []},
    )
    assert store.load_processing_artifact(
        case.case_id, "parsed_document", case.source_file.sha256_digest,
        "synthetic-profile",
    ) == {"lines": []}

    assert manager.delete_case(case.case_id)
    assert store.load_processing_artifact(
        case.case_id, "parsed_document", case.source_file.sha256_digest,
        "synthetic-profile",
    ) is None
    reloaded_store = SQLiteStateStore(database)
    reloaded = CaseManager(
        CatalogRepository(state_store=reloaded_store),
        storage=storage,
        state_store=reloaded_store,
    )
    assert reloaded.get_case(case.case_id) is None
    assert storage.get_file(case.case_id, "request.csv") is None


def test_failed_pdf_case_persists_empty_source_coverage(tmp_path):
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    content = bytes(pdf.output())
    store = SQLiteStateStore(tmp_path / "state" / "rfq.sqlite3")
    manager = CaseManager(CatalogRepository(state_store=store), state_store=store)

    case = manager.create_case_from_upload("empty.pdf", content)

    assert case.status.value == "FAILED"
    assert case.source_coverage
    assert case.source_coverage[0].unit_id == "page:1"
    assert case.source_coverage[0].is_empty is True


def test_header_only_csv_preflight_blocks_case_but_parser_keeps_coverage(tmp_path):
    parsed = SpreadsheetParser().parse(b"MPN,Qty\n", "headers_only.csv")
    assert parsed.source_coverage[0].unit_id == "sheet:Default"
    assert parsed.source_coverage[0].nonempty_regions == 1

    store = SQLiteStateStore(tmp_path / "state" / "rfq.sqlite3")
    storage = DocumentStorage(tmp_path / "source")
    manager = CaseManager(CatalogRepository(state_store=store), storage=storage, state_store=store)
    with pytest.raises(DocumentParserError, match="headers but no RFQ line items"):
        manager.create_case_from_upload("headers_only.csv", b"MPN,Qty\n")
    assert manager.list_cases() == []
    assert store.load_cases() == []
    assert not list(storage.uploads_dir.glob("**/*"))


def test_processing_artifact_cache_skips_oversized_payloads(tmp_path):
    from rfq_assistant.persistence import MAX_PROCESSING_ARTIFACT_BYTES

    store = SQLiteStateStore(tmp_path / "state" / "rfq.sqlite3")
    manager = CaseManager(CatalogRepository(state_store=store), state_store=store)
    case = manager.create_case_from_upload("request.csv", b"MPN,Qty\nPN-123,2\n")

    saved = store.save_processing_artifact(
        case.case_id, "large", case.source_file.sha256_digest, "profile",
        {"text": "x" * MAX_PROCESSING_ARTIFACT_BYTES},
    )

    assert saved is False
    assert store.load_processing_artifact(
        case.case_id, "large", case.source_file.sha256_digest, "profile"
    ) is None


def test_retry_reuses_versioned_parser_artifact_but_not_other_profiles(tmp_path, monkeypatch):
    from rfq_assistant.cases import manager as manager_module
    from rfq_assistant.ingestion.parsers.base import ParsedDocumentResult, ParsedLineDraft
    from rfq_assistant.schemas.models import SourceLocator

    store = SQLiteStateStore(tmp_path / "state" / "rfq.sqlite3")
    manager = CaseManager(CatalogRepository(state_store=store), state_store=store)
    content = b"MPN,Qty\nPN-123,2\n"
    case = manager.enqueue_case_from_upload("request.csv", content)
    job = store.claim_ingestion_job("worker-1")
    assert job is not None
    assert not store.save_processing_artifact(
        case.case_id, "stale-write", case.source_file.sha256_digest,
        "synthetic-profile", {"lines": []}, job_id=job["job_id"],
        worker_id="expired-worker",
    )

    class CountingParser:
        calls = 0
        cache_dependencies = ()

        def cache_profile(self):
            return {"parser": "test.counting", "version": "test-v1"}

        def parse(self, _content, filename):
            self.calls += 1
            return ParsedDocumentResult(lines=[ParsedLineDraft(
                line_number=1,
                raw_text="PN-123 2 EA",
                source_locator=SourceLocator(file_name=filename, row_number=2),
                requested_mpn="PN-123",
                quantity=2,
                unit="EA",
            )], total_lines_detected=1)

    parser = CountingParser()
    monkeypatch.setattr(manager_module, "get_parser", lambda *_args, **_kwargs: parser)
    original_match = manager.matcher.match_line
    fail_once = {"value": True}

    def fail_first_match(*args, **kwargs):
        if fail_once["value"]:
            fail_once["value"] = False
            raise RuntimeError("synthetic interruption after extraction")
        return original_match(*args, **kwargs)

    monkeypatch.setattr(manager.matcher, "match_line", fail_first_match)
    try:
        manager.create_case_from_upload(
            "request.csv", content, _existing_case_id=case.case_id,
            _job_id=job["job_id"], _worker_id="worker-1",
        )
    except RuntimeError as exc:
        assert "synthetic interruption" in str(exc)
    else:
        raise AssertionError("synthetic interruption was not raised")

    retried = manager.create_case_from_upload(
        "request.csv", content, _existing_case_id=case.case_id,
        _job_id=job["job_id"], _worker_id="worker-1",
    )
    assert parser.calls == 1
    assert retried.parse_cache_hit is True
    assert retried.stage_timings_ms["parse_ms"] >= 0

    assert store.load_processing_artifact(
        case.case_id, "parsed_document", case.source_file.sha256_digest, "different-profile"
    ) is None
    assert store.load_processing_artifact(
        "another-case", "parsed_document", case.source_file.sha256_digest,
        retried.processing_profile_sha256,
    ) is None
