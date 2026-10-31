"""Restart recovery checks for local durable RFQ state."""

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion import DocumentStorage
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
        b"manufacturer,mpn,quantity,unit,description\n"
        b"Schneider Electric,LC1D09BD,3,EA,Contactor\n",
        title="Synthetic restart check",
    )
    line = first_manager.get_lines(case.case_id)[0]
    edited = first_manager.update_line(
        case.case_id,
        line.line_id,
        RFQLineItemUpdate(quantity=5, actor="Reviewer A", expected_version=line.version),
    )
    assert edited.quantity == 5

    # Recreate every process-scoped repository while retaining only SQLite and files.
    second_store = SQLiteStateStore(database)
    second_catalog = CatalogRepository(state_store=second_store)
    second_manager = CaseManager(second_catalog, storage=storage, state_store=second_store)

    restored_case = second_manager.get_case(case.case_id)
    restored_line = second_manager.get_lines(case.case_id)[0]
    assert restored_case is not None
    assert restored_case.title == "Synthetic restart check"
    assert restored_line.quantity == 5
    assert restored_line.version == edited.version
    assert restored_line.selected_catalog_sku == "SKU-1"
    assert second_catalog.get_by_sku("SKU-1") is not None
    assert any(event.field_name == "quantity" for event in second_manager.get_audit_trail(case.case_id))
    assert storage.get_file(case.case_id, "request.csv") is not None


def test_delete_case_removes_durable_state_and_file(tmp_path):
    database = tmp_path / "state" / "rfq.sqlite3"
    storage = DocumentStorage(tmp_path / "files")
    store = SQLiteStateStore(database)
    manager = CaseManager(CatalogRepository(state_store=store), storage=storage, state_store=store)
    case = manager.create_case_from_upload("request.csv", b"MPN,Qty\nLC1D09BD,2\n")

    assert manager.delete_case(case.case_id)
    reloaded_store = SQLiteStateStore(database)
    reloaded = CaseManager(
        CatalogRepository(state_store=reloaded_store),
        storage=storage,
        state_store=reloaded_store,
    )
    assert reloaded.get_case(case.case_id) is None
    assert storage.get_file(case.case_id, "request.csv") is None
