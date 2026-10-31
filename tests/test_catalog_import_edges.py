"""Edge-case coverage for all-or-nothing catalog import and normalization indexes."""

import pytest
from pydantic import ValidationError

from rfq_assistant.matching import catalog as catalog_module
from rfq_assistant.matching.catalog import CatalogImportError, CatalogRepository
from rfq_assistant.persistence import SQLiteStateStore
from rfq_assistant.schemas.models import CatalogItem


HEADER = "internal_sku,manufacturer,manufacturer_part_number,description,list_price,stock_qty\n"


def test_clear_removes_in_memory_indexes_and_durable_catalog(tmp_path):
    store = SQLiteStateStore(tmp_path / "state.sqlite3")
    repo = CatalogRepository(state_store=store)
    repo.import_csv((HEADER + "SKU-1,Schneider Electric,PN-1,Relay,1.25,3\n").encode())

    repo.clear()

    assert repo.count() == 0
    assert repo.get_by_sku("SKU-1") is None
    assert repo.get_by_normalized_mpn("PN-1") == []
    assert store.load_catalog() == []


@pytest.mark.parametrize(
    "content,match",
    [
        (b"sku,manufacturer\n", "missing required columns"),
        (
            b"internal_sku,manufacturer,manufacturer_part_number,description,description\n",
            "duplicate column headers",
        ),
        (
            HEADER.encode() + b"SKU-1,Schneider,PN-1,Relay,1,2,extra\n",
            "more fields than its header",
        ),
        (
            (HEADER + "SKU-1,Schneider,PN-1,Relay,1e9999,1\n").encode(),
            "overflowing list_price",
        ),
        (
            (HEADER + "SKU-1,Schneider,PN-1,Relay,1,not-a-stock-count\n").encode(),
            "invalid stock_qty",
        ),
    ],
)
def test_catalog_structure_and_numeric_edges_fail_atomically(content, match):
    repo = CatalogRepository()
    with pytest.raises(CatalogImportError, match=match):
        repo.import_csv(content)
    assert repo.count() == 0


def test_blank_rows_are_skipped_and_empty_rows_do_not_replace_existing_data():
    repo = CatalogRepository()
    content = (
        HEADER + "SKU-1,Schneider Electric,PN-1,Relay,1.5,2\n" + ",,,,,\n"
    ).encode()

    result = repo.import_csv(content)

    assert result["imported"] == 1
    assert result["collisions"] == 0
    assert repo.get_by_sku("SKU-1").list_price == 1.5


def test_catalog_schema_validation_error_is_reported_without_mutation(monkeypatch):
    with pytest.raises(ValidationError) as captured:
        CatalogItem.model_validate({"internal_sku": "incomplete"})
    validation_error = captured.value

    def reject_item(**_kwargs):
        raise validation_error

    monkeypatch.setattr(catalog_module, "CatalogItem", reject_item)
    repo = CatalogRepository()
    with pytest.raises(CatalogImportError, match="row 2 is invalid"):
        repo.import_csv((HEADER + "SKU-1,Schneider,PN-1,Relay,1,2\n").encode())

    assert repo.count() == 0


def test_replace_csv_publishes_one_versioned_snapshot_and_persists_it(tmp_path):
    store = SQLiteStateStore(tmp_path / "catalog.sqlite3")
    repo = CatalogRepository(state_store=store)
    first = (
        HEADER
        + "SKU-1,Schneider Electric,PN-1,Relay,1.25,3\n"
        + "SKU-2,Siemens,PN-2,PLC,5,8\n"
    ).encode()
    first_result = repo.replace_csv(first)
    assert first_result["catalog_version"].startswith("sha256:")
    first_version = first_result["catalog_version"]
    assert all(item.catalog_version == first_version for item in repo.list_all())

    second = (HEADER + "SKU-1,Schneider Electric,PN-1,Updated relay,1.5,4\n").encode()
    second_result = repo.replace_csv(second)

    assert second_result["catalog_version"] != first_version
    assert repo.count() == 1
    assert repo.get_by_sku("SKU-2") is None
    assert repo.get_by_sku("SKU-1").description == "Updated relay"
    restored = CatalogRepository(
        state_store=SQLiteStateStore(tmp_path / "catalog.sqlite3")
    )
    assert restored.list_all() == repo.list_all()


def test_failed_catalog_replacement_leaves_previous_snapshot_intact(
    tmp_path, monkeypatch
):
    store = SQLiteStateStore(tmp_path / "catalog.sqlite3")
    repo = CatalogRepository(state_store=store)
    old_csv = (HEADER + "SKU-1,Schneider Electric,PN-1,Relay,1.25,3\n").encode()
    repo.replace_csv(old_csv)
    old_item = repo.get_by_sku("SKU-1")

    with pytest.raises(CatalogImportError):
        repo.replace_csv((HEADER + "SKU-2,Siemens,PN-2,PLC,not-a-price,2\n").encode())

    assert repo.count() == 1
    assert repo.get_by_sku("SKU-1") == old_item
    assert repo.get_by_sku("SKU-2") is None

    def fail_persist(_items):
        raise OSError("synthetic SQLite write failure")

    monkeypatch.setattr(store, "replace_catalog", fail_persist)
    new_csv = (HEADER + "SKU-2,Siemens,PN-2,PLC,5,2\n").encode()
    with pytest.raises(OSError, match="synthetic SQLite write failure"):
        repo.replace_csv(new_csv)

    assert repo.count() == 1
    assert repo.get_by_sku("SKU-1") == old_item
    assert repo.get_by_sku("SKU-2") is None
