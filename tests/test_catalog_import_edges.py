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
