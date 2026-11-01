"""Regression tests for quotations becoming stale after source RFQ/catalog changes."""

import importlib
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from rfq_assistant.agents.tools import ApprovalGateError, QuotationCommercialService
from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.quotation.validate import ProposedQuote, QuoteLine
from rfq_assistant.schemas.enums import ReviewDecision
from rfq_assistant.schemas.models import CatalogItem, RFQLineItemUpdate


@pytest.fixture
def isolated_api(monkeypatch, tmp_path):
    """Keep adversarial runs isolated from global catalog and prior RFQ tests."""
    api_module = importlib.import_module("rfq_assistant.api.app")
    catalog = CatalogRepository()
    catalog.add_item(
        CatalogItem(
            internal_sku="SKU-SYN-ADVERSARIAL",
            manufacturer="Schneider Electric",
            manufacturer_part_number="LC1D09BD",
            description="Synthetic contactor",
            list_price=40.0,
        )
    )
    manager = CaseManager(catalog=catalog, storage=DocumentStorage(tmp_path / "files"))
    service = QuotationCommercialService()
    monkeypatch.setattr(api_module, "catalog_repo", catalog)
    monkeypatch.setattr(api_module, "case_manager", manager)
    monkeypatch.setattr(api_module, "commercial_service", service)
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("PILOT_API_KEYS", raising=False)
    return TestClient(api_module.app), manager, catalog, service


def create_approved_source(manager):
    case = manager.create_case_from_text("10 pcs Schneider Electric LC1D09BD", title="Synthetic stale quote")
    line = manager.get_lines(case.case_id)[0]
    assert line.selected_catalog_sku == "SKU-SYN-ADVERSARIAL"
    manager.update_line(
        case.case_id,
        line.line_id,
        RFQLineItemUpdate(expected_version=line.version, review_decision=ReviewDecision.APPROVED, actor="Synthetic Reviewer"),
    )
    return case, line


def create_draft(client, case):
    response = client.post(f"/v1/rfqs/{case.case_id}/draft-quote", params={"currency": "USD"})
    assert response.status_code == 200, response.text
    return response.json()


def test_edited_rfq_cannot_approve_old_draft(isolated_api):
    client, manager, _, _ = isolated_api
    case, line = create_approved_source(manager)
    draft = create_draft(client, case)

    manager.update_line(
        case.case_id, line.line_id, RFQLineItemUpdate(expected_version=line.version, quantity=1000.0, actor="Second Reviewer")
    )

    response = client.post(
        f"/v1/quote-drafts/{draft['quote_id']}/approve",
        data={"expected_hash": draft["draft_hash"]},
    )
    assert response.status_code == 409
    assert "changed since this draft" in response.json()["detail"]


def test_approved_quote_cannot_send_after_rfq_edit(isolated_api):
    client, manager, _, _ = isolated_api
    case, line = create_approved_source(manager)
    draft = create_draft(client, case)
    approve = client.post(
        f"/v1/quote-drafts/{draft['quote_id']}/approve",
        data={"expected_hash": draft["draft_hash"]},
    )
    assert approve.status_code == 200, approve.text

    manager.update_line(
        case.case_id, line.line_id, RFQLineItemUpdate(expected_version=line.version, unit="BOX", actor="Second Reviewer")
    )

    response = client.post(
        f"/v1/approved-quotes/{draft['quote_id']}/send",
        data={"expected_hash": draft["draft_hash"]},
    )
    assert response.status_code == 409
    assert "changed since this draft" in response.json()["detail"]


def test_catalog_price_change_invalidates_quote_snapshot(isolated_api):
    client, manager, catalog, _ = isolated_api
    case, _ = create_approved_source(manager)
    draft = create_draft(client, case)

    catalog.get_by_sku("SKU-SYN-ADVERSARIAL").list_price = 99.0
    response = client.post(
        f"/v1/quote-drafts/{draft['quote_id']}/approve",
        data={"expected_hash": draft["draft_hash"]},
    )
    assert response.status_code == 409
    assert "changed since this draft" in response.json()["detail"]


def test_deleted_rfq_cannot_authorize_saved_draft(isolated_api):
    client, manager, _, _ = isolated_api
    case, _ = create_approved_source(manager)
    draft = create_draft(client, case)
    assert manager.delete_case(case.case_id)

    response = client.post(
        f"/v1/quote-drafts/{draft['quote_id']}/approve",
        data={"expected_hash": draft["draft_hash"]},
    )
    assert response.status_code == 409
    assert "no longer exists" in response.json()["detail"]


def test_registering_same_quote_id_revokes_prior_approval():
    service = QuotationCommercialService()
    line = QuoteLine(
        line_no=1,
        requested_mpn="LC1D09BD",
        catalogue_part_id="SKU-SYN",
        quantity=Decimal("10"),
        unit_price=Decimal("40.0"),
        currency="USD",
        source_price_id="CAT-SYN",
        match_status="exact",
        requires_human_review=False,
    )
    quote = ProposedQuote(quote_id="QUOTE-SYN", case_id="RFQ-SYN", lines=[line])
    service.register_draft(quote)
    approved = service.approve_draft(quote.quote_id, quote.draft_hash, "Reviewer")
    assert approved.commercial_status == "APPROVED"

    replacement = ProposedQuote(quote_id="QUOTE-SYN", case_id="RFQ-SYN", lines=[line.model_copy()])
    service.register_draft(replacement)
    assert not replacement.is_approved
    assert replacement.approved_by is None

    with pytest.raises(ApprovalGateError, match="has not been approved"):
        service.send_approved_quote(replacement.quote_id, replacement.draft_hash, "Sender")
