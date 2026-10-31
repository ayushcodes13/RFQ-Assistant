"""Catalog snapshot changes must invalidate and explicitly refresh old matches."""

import pytest

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.exports import ExportGenerator, ExportValidationError
from rfq_assistant.ingestion import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.persistence import SQLiteStateStore
from rfq_assistant.schemas.enums import AuditAction, CaseStatus, ReviewDecision
from rfq_assistant.schemas.models import ExportRequest, RFQLineItemUpdate, RematchLineRequest


CATALOG_HEADER = "internal_sku,manufacturer,manufacturer_part_number,description,list_price,stock_qty\n"


def test_restart_persists_recovered_catalog_version_for_legacy_line(tmp_path):
    database = tmp_path / "rfq.sqlite3"
    store = SQLiteStateStore(database)
    catalog = CatalogRepository(state_store=store)
    version = catalog.replace_csv(
        (CATALOG_HEADER + "SKU-1,Schneider Electric,LC1D09BD,Contactor,40,10\n").encode()
    )["catalog_version"]
    manager = CaseManager(
        catalog,
        storage=DocumentStorage(tmp_path / "uploads"),
        state_store=store,
    )
    case = manager.create_case_from_upload(
        "request.csv",
        b"manufacturer,mpn,quantity,description\n"
        b"Schneider Electric,LC1D09BD,2,Contactor\n",
    )
    legacy_line = manager.get_lines(case.case_id)[0]
    legacy_line.matched_catalog_version = None
    store.save_case_snapshot(
        manager.get_case(case.case_id),
        [legacy_line],
        manager.get_audit_trail(case.case_id),
    )

    reloaded_store = SQLiteStateStore(database)
    reloaded_catalog = CatalogRepository(state_store=reloaded_store)
    CaseManager(
        reloaded_catalog,
        storage=DocumentStorage(tmp_path / "uploads"),
        state_store=reloaded_store,
    )

    persisted_line = reloaded_store.load_lines(case.case_id)[0]
    assert persisted_line["matched_catalog_version"] == version


def test_catalog_version_change_requires_rematch_and_revokes_approval(tmp_path):
    database = tmp_path / "rfq.sqlite3"
    store = SQLiteStateStore(database)
    catalog = CatalogRepository(state_store=store)
    first_snapshot = (
        CATALOG_HEADER
        + "SKU-1,Schneider Electric,LC1D09BD,Contactor,40,10\n"
    ).encode()
    old_version = catalog.replace_csv(first_snapshot)["catalog_version"]
    storage = DocumentStorage(tmp_path / "uploads")
    manager = CaseManager(catalog, storage=storage, state_store=store)
    case = manager.create_case_from_upload(
        "request.csv",
        b"manufacturer,mpn,quantity,description\n"
        b"Schneider Electric,LC1D09BD,2,Contactor\n",
    )
    line = manager.get_lines(case.case_id)[0]
    assert line.matched_catalog_version == old_version

    approved = manager.update_line(
        case.case_id,
        line.line_id,
        RFQLineItemUpdate(
            expected_version=line.version,
            review_decision=ReviewDecision.APPROVED,
            actor="Reviewer",
        ),
    )
    assert approved.review_decision == ReviewDecision.APPROVED
    assert manager.get_case(case.case_id).status == CaseStatus.READY_TO_EXPORT

    second_snapshot = (
        CATALOG_HEADER
        + "SKU-1,Schneider Electric,LC1D09BD,Revised contactor,42,8\n"
    ).encode()
    new_version = catalog.replace_csv(second_snapshot)["catalog_version"]
    manager.handle_catalog_replacement("Catalog Admin", new_version)

    stale_line = manager.get_lines(case.case_id)[0]
    assert stale_line.catalog_rematch_required is True
    assert stale_line.matched_catalog_version == old_version
    assert stale_line.candidates[0].catalog_item.description == "Contactor"
    assert stale_line.review_decision == ReviewDecision.APPROVED
    assert manager.get_case(case.case_id).status == CaseStatus.NEEDS_REVIEW
    assert manager.get_case(case.case_id).unresolved_count == 1
    assert manager.get_review_plan(case.case_id).exception_line_ids == [line.line_id]

    generator = ExportGenerator(catalog, base_export_dir=tmp_path / "exports")
    with pytest.raises(ExportValidationError, match="rematch required"):
        generator.generate_export(
            manager.get_case(case.case_id),
            [stale_line],
            ExportRequest(case_id=case.case_id, allow_partial=False),
        )

    reloaded_store = SQLiteStateStore(database)
    reloaded_catalog = CatalogRepository(state_store=reloaded_store)
    reloaded_manager = CaseManager(
        reloaded_catalog,
        storage=storage,
        state_store=reloaded_store,
    )
    restored_line = reloaded_manager.get_lines(case.case_id)[0]
    assert restored_line.catalog_rematch_required is True
    assert reloaded_manager.get_case(case.case_id).status == CaseStatus.NEEDS_REVIEW

    rematched = reloaded_manager.rematch_line(
        case.case_id,
        line.line_id,
        RematchLineRequest(expected_version=restored_line.version, actor="Reviewer"),
    )

    assert rematched.catalog_rematch_required is False
    assert rematched.matched_catalog_version == new_version
    assert rematched.candidates[0].catalog_item.description == "Revised contactor"
    assert rematched.review_decision == ReviewDecision.PENDING
    assert rematched.reviewed_by is None
    assert reloaded_manager.get_case(case.case_id).status == CaseStatus.NEEDS_REVIEW
    assert any(
        event.action == AuditAction.CATALOG_REMATCHED
        for event in reloaded_manager.get_audit_trail(case.case_id)
    )
