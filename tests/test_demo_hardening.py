"""Regressions for clean demo intake and optimistic review concurrency."""

import pytest
from pydantic import ValidationError

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion import DocumentParserError, DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.schemas.models import RFQLineItemUpdate


@pytest.fixture
def manager(tmp_path):
    return CaseManager(catalog=CatalogRepository(), storage=DocumentStorage(tmp_path / "uploads"))


@pytest.mark.parametrize("text", ["", " \n\t  ", "Part Number | Manufacturer | Quantity\n"])
def test_empty_or_header_only_text_is_rejected_before_case_or_file_creation(manager, text):
    with pytest.raises(DocumentParserError):
        manager.create_case_from_text(text)
    assert manager.list_cases() == []
    assert list(manager.storage.uploads_dir.rglob("*")) == []


def test_oversized_region_count_is_rejected_before_case_or_file_creation(manager):
    text = "\n".join(f"unrecognized row {i} without item clues" for i in range(600))
    with pytest.raises(DocumentParserError, match="more than 500"):
        manager.create_case_from_text(text)
    assert manager.list_cases() == []
    assert list(manager.storage.uploads_dir.rglob("*")) == []


def test_unfamiliar_prose_still_reaches_manual_review_path(manager):
    case = manager.create_case_from_text("Could you help us source the unusual sensor from our legacy line?")
    assert manager.get_case(case.case_id) is not None
    assert manager.get_lines(case.case_id)


def test_review_update_requires_version_and_rejects_stale_version(manager):
    with pytest.raises(ValidationError):
        RFQLineItemUpdate(quantity=3)
    case = manager.create_case_from_text("10 pcs LC1D09BD Schneider")
    line = manager.get_lines(case.case_id)[0]
    update = RFQLineItemUpdate(expected_version=line.version, quantity=11)
    manager.update_line(case.case_id, line.line_id, update)
    with pytest.raises(ValueError, match="Stale state / conflict"):
        manager.update_line(case.case_id, line.line_id, update)
