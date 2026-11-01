"""XLSX preflight must not duplicate the expensive full worker row scan."""

from types import SimpleNamespace

import pytest

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.parsers.base import DocumentParserError
from rfq_assistant.schemas.enums import SourceType


class SyntheticWorkbook:
    def __init__(self, sheet):
        self.worksheets = [sheet]
        self.closed = False

    def close(self):
        self.closed = True


def test_preflight_short_circuits_after_first_real_item(monkeypatch):
    def first_rows(*, values_only):
        assert values_only
        yield ("MPN", "Quantity")
        yield ("LC1D09BD", 10)
        raise AssertionError("preflight must not scan the rest of the BOM")

    workbook = SyntheticWorkbook(SimpleNamespace(iter_rows=first_rows))
    monkeypatch.setattr("rfq_assistant.cases.manager.load_workbook", lambda *a, **k: workbook)
    CaseManager._validate_intake_regions("synthetic.xlsx", SourceType.XLSX, b"not-real-xlsx")
    assert workbook.closed


def test_preflight_still_rejects_header_only_workbook(monkeypatch):
    class HeaderSheet:
        def iter_rows(self, *, values_only):
            assert values_only
            yield ("MPN", "Quantity")
    workbook = SyntheticWorkbook(HeaderSheet())
    monkeypatch.setattr("rfq_assistant.cases.manager.load_workbook", lambda *a, **k: workbook)
    with pytest.raises(DocumentParserError, match="headers but no RFQ line items"):
        CaseManager._validate_intake_regions("synthetic.xlsx", SourceType.XLSX, b"not-real-xlsx")
    assert workbook.closed
