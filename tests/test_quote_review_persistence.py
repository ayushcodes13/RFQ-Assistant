"""Quote review decisions remain version-bound across local SQLite restarts."""

from decimal import Decimal

import pytest

from rfq_assistant.agents.tools import ApprovalGateError, QuotationCommercialService
from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.persistence import SQLiteStateStore
from rfq_assistant.quotation.validate import ProposedQuote, QuoteLine


def setup_quote(tmp_path):
    store = SQLiteStateStore(tmp_path / "quote-review.sqlite3")
    manager = CaseManager(
        catalog=CatalogRepository(),
        storage=DocumentStorage(tmp_path / "source-files"),
        state_store=store,
    )
    case = manager.create_case_from_text(
        "2 pcs Schneider Electric LC1D09BD", title="Synthetic quote review"
    )
    line = QuoteLine(
        line_no=1,
        requested_mpn="LC1D09BD",
        requested_manufacturer="Schneider Electric",
        catalogue_part_id="SKU-SYN",
        quantity=Decimal("2"),
        unit="EA",
        unit_price=Decimal("5.25"),
        currency="USD",
        source_price_id="CAT-synthetic-v1-SKU-SYN",
        match_status="exact",
        requires_human_review=False,
    )
    draft = ProposedQuote(
        quote_id=f"QUOTE-{case.case_id}",
        case_id=case.case_id,
        customer_name="Synthetic Customer",
        currency="USD",
        lines=[line],
    )
    return store, manager, draft


def reopen(store):
    return QuotationCommercialService(state_store=SQLiteStateStore(store.database_path))


def test_approval_survives_restart_but_replacement_revokes_it(tmp_path, monkeypatch):
    monkeypatch.delenv("REQUIRE_REAL_TRANSPORT", raising=False)
    store, _manager, draft = setup_quote(tmp_path)
    service = QuotationCommercialService(state_store=store)
    saved = service.register_draft(draft)
    decision = service.approve_draft(saved.quote_id, saved.draft_hash, "Authorized reviewer")

    restarted = reopen(store)
    restored_draft = restarted.get_draft(saved.quote_id)
    assert restored_draft is not None
    assert restored_draft.is_approved
    assert restored_draft.approved_by == "Authorized reviewer"
    assert restarted._approvals[saved.quote_id].approved_hash == decision.approved_hash
    # Sending is simulated only; no external transport should be invoked.
    simulation = restarted.send_approved_quote(
        saved.quote_id, saved.draft_hash, "Authorized reviewer"
    )
    assert simulation["outbound_transport_invoked"] is False

    replacement = ProposedQuote(
        quote_id=saved.quote_id,
        case_id=saved.case_id,
        currency="USD",
        lines=[saved.lines[0].model_copy(deep=True)],
    )
    restarted.register_draft(replacement)
    reopened_again = reopen(store)
    assert not reopened_again.get_draft(saved.quote_id).is_approved
    assert saved.quote_id not in reopened_again._approvals
    with pytest.raises(ApprovalGateError, match="not been approved"):
        reopened_again.send_approved_quote(
            saved.quote_id, replacement.draft_hash, "Authorized reviewer"
        )
    assert [event["commercial_status"] for event in store.load_quote_decisions()] == [
        "APPROVED", "REVOKED"
    ]


def test_rejection_reason_is_durable_and_blocks_send(tmp_path):
    store, _manager, draft = setup_quote(tmp_path)
    service = QuotationCommercialService(state_store=store)
    saved = service.register_draft(draft)
    rejected = service.reject_draft(
        saved.quote_id, "Authorized reviewer", "Quantity needs confirmation"
    )

    restarted = reopen(store)
    record = restarted._approvals[saved.quote_id]
    assert rejected.reason == "Quantity needs confirmation"
    assert record.commercial_status == "REJECTED"
    assert record.reason == "Quantity needs confirmation"
    assert not restarted.get_draft(saved.quote_id).is_approved
    with pytest.raises(ApprovalGateError, match="has not been approved"):
        restarted.send_approved_quote(
            saved.quote_id, saved.draft_hash, "Authorized reviewer"
        )


def test_quote_decisions_removed_with_deleted_case(tmp_path):
    store, manager, draft = setup_quote(tmp_path)
    service = QuotationCommercialService(state_store=store)
    saved = service.register_draft(draft)
    service.reject_draft(saved.quote_id, "Authorized reviewer", "Synthetic correction")
    assert len(store.load_quote_decisions()) == 1
    assert manager.delete_case(saved.case_id)
    assert store.load_quote_decisions() == []
    assert store.load_quote_drafts() == []
