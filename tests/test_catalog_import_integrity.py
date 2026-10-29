"""Adversarial item-master import tests: no silent skips and no partial mutations."""

import pytest

from rfq_assistant.matching.catalog import CatalogImportError, CatalogRepository
from rfq_assistant.matching.engine import ExactMatchEngine
from rfq_assistant.schemas.enums import MatchStatus


HEADER = "internal_sku,manufacturer,manufacturer_part_number,description,list_price,stock_qty\n"


def test_atomic_import_rejects_bad_final_row_without_partial_commit():
    repo = CatalogRepository()
    file = (
        HEADER
        + "SYN-1,Schneider Electric,LC1D09BD,Contactor,40,10\n"
        + "SYN-2,Siemens,6ES7214-1AG40-0XB0,PLC,not-a-price,10\n"
    ).encode()
    with pytest.raises(CatalogImportError, match="invalid list_price"):
        repo.import_csv(file)
    assert repo.count() == 0
    assert repo.get_by_normalized_mpn("LC1D09BD") == []


@pytest.mark.parametrize("line,reason", [
    ("SYN-2,Siemens,6ES7214-1AG40-0XB0,PLC,NaN,10", "nonnegative list_price"),
    ("SYN-2,Siemens,6ES7214-1AG40-0XB0,PLC,Infinity,10", "nonnegative list_price"),
    ("SYN-2,Siemens,6ES7214-1AG40-0XB0,PLC,-5,10", "nonnegative list_price"),
    ("SYN-2,Siemens,6ES7214-1AG40-0XB0,PLC,50,-1", "whole-number stock_qty"),
    ("SYN-2,Siemens,6ES7214-1AG40-0XB0,PLC,50,2.5", "whole-number stock_qty"),
    ("SYN-2,,6ES7214-1AG40-0XB0,PLC,50,2", "nonempty SKU"),
    ("SYN-2,Siemens,,PLC,50,2", "nonempty SKU"),
])
def test_invalid_rows_fail_instead_of_being_silently_ignored(line, reason):
    repo = CatalogRepository()
    with pytest.raises(CatalogImportError, match=reason):
        repo.import_csv((HEADER + line + "\n").encode())
    assert repo.count() == 0


def test_failed_import_does_not_mutate_existing_item_master():
    repo = CatalogRepository()
    existing = (HEADER + "SYN-1,Schneider Electric,LC1D09BD,Contactor,40,10\n").encode()
    assert repo.import_csv(existing)["imported"] == 1
    broken = (
        HEADER
        + "SYN-2,Siemens,6ES7214-1AG40-0XB0,PLC,55,10\n"
        + "SYN-3,ABB,NEW-123,Invalid,-2,4\n"
    ).encode()
    with pytest.raises(CatalogImportError):
        repo.import_csv(broken)
    assert repo.count() == 1
    assert repo.get_by_sku("SYN-2") is None
    match = ExactMatchEngine(repo).match_line("LC1D09BD", "Schneider Electric")
    assert match.match_status == MatchStatus.EXACT_MATCH


def test_repeated_sku_inside_upload_is_rejected_atomically():
    repo = CatalogRepository()
    repeated = (
        HEADER
        + "SYN-1,Schneider Electric,LC1D09BD,Contactor,40,10\n"
        + "SYN-1,Siemens,6ES7214-1AG40-0XB0,PLC,55,10\n"
    ).encode()
    with pytest.raises(CatalogImportError, match="repeats SKU"):
        repo.import_csv(repeated)
    assert repo.count() == 0


def test_existing_sku_import_is_idempotent_and_bom_header_can_include_bom():
    repo = CatalogRepository()
    sample = (HEADER + "SYN-1,Schneider Electric,LC1D09BD,Contactor,40,10\n").encode()
    assert repo.import_csv(sample)["imported"] == 1
    result = repo.import_csv(sample)
    assert result["imported"] == 0
    assert result["duplicates"] == 1
    assert repo.count() == 1
    assert repo.get_by_sku("SYN-1").list_price == 40.0


def test_header_only_catalog_rejected():
    repo = CatalogRepository()
    with pytest.raises(CatalogImportError, match="no importable item"):
        repo.import_csv(HEADER.encode())
