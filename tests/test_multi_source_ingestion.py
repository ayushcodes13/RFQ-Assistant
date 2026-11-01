"""Synthetic tests for parent RFQs composed from multiple source documents."""

import importlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from rfq_assistant.cases.manager import MAX_SOURCE_DOCUMENTS_PER_CASE, CaseManager
from rfq_assistant.ingestion import DocumentStorage, UploadValidationError
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.persistence import SQLiteStateStore
from rfq_assistant.schemas.enums import CaseStatus

LINE_A = b"1. 4 units Schneider Electric LC1D09BD contactor"
LINE_B = b"1. 7 units Schneider Electric LC1D09BD contactor"


def test_multiple_sources_keep_one_case_and_flag_quantity_conflict(tmp_path):
    manager = CaseManager(
        CatalogRepository(),
        storage=DocumentStorage(tmp_path / "storage"),
    )

    case = manager.create_case_from_uploads([
        ("buyer-email.txt", LINE_A),
        ("parts-list.txt", LINE_B),
    ])

    lines = manager.get_lines(case.case_id)
    assert case.status == CaseStatus.NEEDS_REVIEW
    assert len(case.source_documents) == 2
    assert [document.processing_status for document in case.source_documents] == ["processed", "processed"]
    assert [document.line_count for document in case.source_documents] == [1, 1]
    assert {line.case_id for line in lines} == {case.case_id}
    assert [line.line_number for line in lines] == [1, 2]
    assert {line.source_locator.source_file_id for line in lines} == {
        document.source_file.file_id for document in case.source_documents
    }
    assert all("SOURCE_QUANTITY_CONFLICT" in {warning.code for warning in line.extraction_warnings} for line in lines)
    assert any(warning.code == "SOURCE_QUANTITY_CONFLICT" for warning in case.document_warnings)


def test_duplicate_attachment_is_accounted_for_without_duplicate_lines(tmp_path):
    manager = CaseManager(CatalogRepository(), storage=DocumentStorage(tmp_path / "storage"))

    case = manager.create_case_from_uploads([
        ("part-list-a.txt", LINE_A),
        ("part-list-copy.txt", LINE_A),
    ])

    assert len(manager.get_lines(case.case_id)) == 1
    assert [document.processing_status for document in case.source_documents] == ["processed", "duplicate"]
    assert case.source_documents[1].error_code == "DUPLICATE_SOURCE"
    assert any(warning.code == "DUPLICATE_SOURCE" for warning in case.document_warnings)


def test_same_mpn_with_different_manufacturer_is_a_visible_conflict(tmp_path):
    manager = CaseManager(CatalogRepository(), storage=DocumentStorage(tmp_path / "storage"))
    case = manager.create_case_from_uploads([
        ("source-a.txt", b"4 pcs Schneider Electric LC1D09BD contactor"),
        ("source-b.txt", b"4 pcs Siemens LC1D09BD contactor"),
    ])
    assert case.status == CaseStatus.NEEDS_REVIEW
    assert any(w.code == "SOURCE_MANUFACTURER_CONFLICT" for w in case.document_warnings)
    assert all(
        any(w.code == "SOURCE_MANUFACTURER_CONFLICT" for w in line.extraction_warnings)
        for line in manager.get_lines(case.case_id)
    )


def test_revision_and_different_part_number_conflicts_are_review_blockers(tmp_path):
    manager = CaseManager(CatalogRepository(), storage=DocumentStorage(tmp_path / "storage"))
    revision_case = manager.create_case_from_uploads([
        ("rev-a.txt", b"4 pcs Schneider Electric LC1D09BD contactor Rev A"),
        ("rev-b.txt", b"4 pcs Schneider Electric LC1D09BD contactor Revision B"),
    ])
    assert any(w.code == "SOURCE_REVISION_CONFLICT" for w in revision_case.document_warnings)
    assert all(
        any(w.code == "SOURCE_REVISION_CONFLICT" for w in line.extraction_warnings)
        for line in manager.get_lines(revision_case.case_id)
    )

    part_case = manager.create_case_from_uploads([
        ("part-a.txt", b"Schneider Electric LC1D09BD high performance motor contactor"),
        ("part-b.txt", b"Schneider Electric LC1D09BE high performance motor contactor"),
    ])
    assert any(w.code == "SOURCE_PART_NUMBER_CONFLICT" for w in part_case.document_warnings)
    assert all(
        any(w.code == "SOURCE_PART_NUMBER_CONFLICT" for w in line.extraction_warnings)
        for line in manager.get_lines(part_case.case_id)
    )


def test_failed_attachment_does_not_discard_successful_source_lines(tmp_path):
    manager = CaseManager(CatalogRepository(), storage=DocumentStorage(tmp_path / "storage"))

    case = manager.create_case_from_uploads([
        ("parts.txt", LINE_A),
        ("empty-valid-pdf.pdf", b"%PDF-1.4\n%%EOF"),
    ])

    assert case.status == CaseStatus.NEEDS_REVIEW
    assert len(manager.get_lines(case.case_id)) == 1
    assert case.source_documents[0].processing_status == "processed"
    assert case.source_documents[1].processing_status == "failed"
    assert case.source_documents[1].error_code
    assert any(warning.severity == "error" for warning in case.document_warnings)


def test_retrying_failed_source_preserves_existing_successful_lines(tmp_path):
    manager = CaseManager(CatalogRepository(), storage=DocumentStorage(tmp_path / "storage"))
    case = manager.create_case_from_uploads([
        ("parts.txt", LINE_A),
        ("empty-valid.pdf", b"%PDF-1.4\n%%EOF"),
    ])
    source_id = case.source_documents[1].source_file.file_id
    before = [(line.line_id, line.requested_mpn) for line in manager.get_lines(case.case_id)]

    retried = manager.retry_source_document(case.case_id, source_id, "Synthetic Reviewer")

    assert retried.source_documents[1].processing_status == "failed"
    assert [(line.line_id, line.requested_mpn) for line in manager.get_lines(case.case_id)] == before


def test_queued_multi_source_case_processes_under_one_durable_job(tmp_path):
    store = SQLiteStateStore(tmp_path / "state.sqlite3")
    manager = CaseManager(
        CatalogRepository(),
        storage=DocumentStorage(tmp_path / "storage"),
        state_store=store,
    )
    queued = manager.create_case_from_uploads(
        [("parts-a.txt", LINE_A), ("parts-b.txt", LINE_B)],
        defer_processing=True,
    )
    job = store.claim_ingestion_job("worker-one")
    assert job and job["case_id"] == queued.case_id

    processed = manager.process_pending_case(
        queued.case_id,
        job_id=job["job_id"],
        worker_id="worker-one",
    )

    restored = store.load_case_snapshot(queued.case_id)
    assert processed.status == CaseStatus.NEEDS_REVIEW
    assert len(manager.get_lines(queued.case_id)) == 2
    assert restored is not None
    assert len(restored["case"]["source_documents"]) == 2
    assert [source["processing_status"] for source in restored["case"]["source_documents"]] == ["processed", "processed"]


def test_multi_source_limits_reject_too_many_documents(tmp_path):
    manager = CaseManager(CatalogRepository(), storage=DocumentStorage(tmp_path / "storage"))
    with pytest.raises(UploadValidationError, match="between 2"):
        manager.create_case_from_uploads([
            (f"item-{index}.txt", LINE_A)
            for index in range(MAX_SOURCE_DOCUMENTS_PER_CASE + 1)
        ])


def test_api_accepts_one_email_and_multiple_attachments_in_one_case(monkeypatch, tmp_path):
    api = importlib.import_module("rfq_assistant.api.app")

    manager = CaseManager(CatalogRepository(), storage=DocumentStorage(tmp_path / "storage"))
    monkeypatch.setattr(api, "case_manager", manager)
    monkeypatch.setattr(api, "ASYNC_INGEST_ENABLED", False)
    monkeypatch.setattr(
        api,
        "clamav_scanner",
        SimpleNamespace(
            protected_mode=False,
            scan_bytes=lambda *_args, **_kwargs: SimpleNamespace(
                is_clean=True,
                scanned=True,
                quarantined=False,
                threat_name=None,
                engine="synthetic-test-scanner",
            ),
        ),
    )
    client = TestClient(api.app)

    response = client.post(
        "/api/rfqs",
        data={"pasted_text": "1. 3 units Siemens 6ES7223-1BL32-0XB0 digital module"},
        files=[
            ("files", ("parts-a.txt", LINE_A, "text/plain")),
            ("files", ("parts-b.txt", LINE_B, "text/plain")),
        ],
    )

    assert response.status_code == 200, response.text
    case = response.json()
    assert len(case["source_documents"]) == 3
    assert case["line_count"] == 3
    assert {line.case_id for line in manager.get_lines(case["case_id"])} == {case["case_id"]}


def test_secondary_source_download_uses_private_storage_key(monkeypatch, tmp_path):
    api = importlib.import_module("rfq_assistant.api.app")
    manager = CaseManager(CatalogRepository(), storage=DocumentStorage(tmp_path / "storage"))
    monkeypatch.setattr(api, "case_manager", manager)
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    first = b"1. 4 units Schneider Electric LC1D09BD contactor"
    second = b"2. 7 units Phoenix Contact 2900364 terminal block"
    case = manager.create_case_from_uploads([
        ("buyer_parts_a.txt", first),
        ("buyer_parts_b.txt", second),
    ])
    document = case.source_documents[1]
    response = TestClient(api.app).get(
        f"/api/rfqs/{case.case_id}/source",
        params={"source_file_id": document.source_file.file_id},
    )
    assert response.status_code == 200, response.text
    assert response.content == second
    assert response.headers["content-disposition"].endswith('filename="buyer_parts_b.txt"')
