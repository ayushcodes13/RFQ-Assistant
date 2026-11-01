"""Synthetic tests for deterministic retrieval plus Luna evidence mapping."""

import importlib
import json
from decimal import Decimal

from fastapi.testclient import TestClient

from rfq_assistant.agents.tools import QuotationCommercialService
from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.ai_extraction import GroundedLLMExtractor
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.persistence import SQLiteStateStore
from rfq_assistant.quotation.proposal import (
    GroundedQuoteProposalService,
    QuoteProposalError,
)
from rfq_assistant.quotation.validate import (
    ProposedQuote,
    QuoteLine,
    validate_proposed_quote,
)
from rfq_assistant.schemas.enums import ReviewDecision
from rfq_assistant.schemas.models import CatalogItem, RFQLineItemUpdate


class EvidenceEchoLuna:
    model = "gpt-6-luna"

    def __init__(self, *, wrong_quote=False):
        self.calls = 0
        self.wrong_quote = wrong_quote

    def complete(self, *, system, user):
        self.calls += 1
        assert "Do not search for" in system
        payload = json.loads(user)
        lines = []
        for buyer, distributor in zip(payload["buyer_lines"], payload["retrieved_distributor_records"], strict=True):
            lines.append({
                "line_no": buyer["line_no"],
                "buyer_source_id": buyer["source_id"],
                "buyer_evidence": "not present in the buyer source" if self.wrong_quote else buyer["text"],
                "distributor_source_id": distributor["source_id"],
                "distributor_evidence": distributor["evidence_text"],
            })
        return json.dumps({"lines": lines})


def test_quote_proposal_only_maps_retrieved_sources_and_api_owns_values(tmp_path, monkeypatch):
    api = importlib.import_module("rfq_assistant.api.app")
    catalog = CatalogRepository()
    catalog.add_item(CatalogItem(
        internal_sku="SKU-SYN-1",
        manufacturer="Schneider Electric",
        manufacturer_part_number="LC1D09BD",
        description="Synthetic contactor",
        list_price=42.5,
        currency="USD",
        stock_qty=20,
        catalog_version="synthetic-v1",
    ))
    provider = EvidenceEchoLuna()
    manager = CaseManager(
        catalog=catalog,
        storage=DocumentStorage(tmp_path / "files"),
        llm_extractor=GroundedLLMExtractor(provider),
    )
    case = manager.create_case_from_text("10 pcs Schneider Electric LC1D09BD", title="Synthetic grounded quote")
    line = manager.get_lines(case.case_id)[0]
    manager.update_line(case.case_id, line.line_id, RFQLineItemUpdate(
        expected_version=line.version,
        review_decision=ReviewDecision.APPROVED,
        actor="Synthetic reviewer",
    ))

    monkeypatch.setattr(api, "catalog_repo", catalog)
    monkeypatch.setattr(api, "case_manager", manager)
    monkeypatch.setattr(api, "commercial_service", QuotationCommercialService())
    monkeypatch.setattr(api, "catalog_update_service", type("NoUpdates", (), {"list_proposals": lambda self: []})())
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("PILOT_API_KEYS", raising=False)

    response = TestClient(api.app).post(f"/v1/rfqs/{case.case_id}/draft-quote")
    assert response.status_code == 200, response.text
    draft = response.json()
    assert provider.calls == 1
    assert draft["quote_proposal_status"] == "grounded"
    assert Decimal(draft["total_amount"]) == Decimal(425)
    quote_line = draft["lines"][0]
    assert quote_line["unit_price"] == "42.5"
    assert Decimal(quote_line["line_total"]) == Decimal(425)
    assert len(quote_line["sources"]) == 2
    assert quote_line["sources"][0]["text_excerpt"] == "10 pcs Schneider Electric LC1D09BD"
    assert "list price 42.5 USD" in quote_line["sources"][1]["text_excerpt"]


def test_quote_evidence_mapper_rejects_nonverbatim_buyer_citation():
    client = EvidenceEchoLuna(wrong_quote=True)
    service = GroundedQuoteProposalService(client)
    buyer = [{"line_no": 1, "source_id": "BUYER-1", "text": "2 pcs Phoenix Contact 2900364", "requested_mpn": "2900364", "quantity": "2"}]
    distributor = [{"line_no": 1, "source_id": "CAT-1", "evidence_text": "SKU S1 MPN 2900364 list price 3.25 USD", "unit_price": "3.25", "currency": "USD"}]
    try:
        service.propose(buyer_lines=buyer, distributor_records=distributor)
    except QuoteProposalError as exc:
        assert "not verbatim" in str(exc)
    else:
        raise AssertionError("Non-verbatim buyer citation must fail closed")


def test_quote_validation_blocks_failed_second_model_stage():
    quote = ProposedQuote(
        quote_id="QUOTE-SYNTHETIC",
        case_id="RFQ-SYNTHETIC",
        quote_proposal_status="failed",
        lines=[QuoteLine(
            line_no=1,
            requested_mpn="LC1D09BD",
            quantity="1",
            unit_price="42.50",
            source_price_id="CAT-v1-SKU1",
            match_status="exact",
            requires_human_review=False,
        )],
    )
    assert any("quote proposal stage failed" in error for error in validate_proposed_quote(quote))


def test_quote_draft_preserves_missing_quantity_as_review_blocker():
    quote = ProposedQuote(
        quote_id="QUOTE-MISSING-QTY",
        case_id="RFQ-MISSING-QTY",
        lines=[QuoteLine(
            line_no=1,
            requested_mpn="LC1D09BD",
            quantity=None,
            unit_price="42.50",
            source_price_id="CAT-v1-SKU1",
            match_status="exact",
        )],
    )
    assert quote.lines[0].line_total is None
    assert quote.total_amount is None
    assert any("Quantity is missing" in error for error in validate_proposed_quote(quote))


def test_draft_quote_api_returns_missing_quantity_instead_of_failing(tmp_path, monkeypatch):
    api = importlib.import_module("rfq_assistant.api.app")
    catalog = CatalogRepository()
    catalog.add_item(CatalogItem(
        internal_sku="SKU-SYN-MISSING-QTY",
        manufacturer="Schneider Electric",
        manufacturer_part_number="LC1D09BD",
        description="Synthetic contactor",
        list_price=42.5,
        currency="USD",
        stock_qty=20,
        catalog_version="synthetic-v1",
    ))
    manager = CaseManager(catalog=catalog, storage=DocumentStorage(tmp_path / "files"))
    case = manager.create_case_from_text("Schneider Electric LC1D09BD", title="Missing quantity")
    assert manager.get_lines(case.case_id)
    assert manager.get_lines(case.case_id)[0].quantity is None

    monkeypatch.setattr(api, "catalog_repo", catalog)
    monkeypatch.setattr(api, "case_manager", manager)
    monkeypatch.setattr(api, "commercial_service", QuotationCommercialService())
    monkeypatch.setattr(api, "catalog_update_service", type("NoUpdates", (), {"list_proposals": lambda self: []})())
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("PILOT_API_KEYS", raising=False)

    response = TestClient(api.app).post(f"/v1/rfqs/{case.case_id}/draft-quote")
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["lines"][0]["quantity"] is None
    assert draft["lines"][0]["line_total"] is None
    assert any("Quantity is missing" in error for error in draft["validation_errors"])


def test_quote_draft_survives_commercial_service_restart(tmp_path):
    store = SQLiteStateStore(tmp_path / "quote-state.sqlite3")
    manager = CaseManager(catalog=CatalogRepository(), storage=DocumentStorage(tmp_path / "files"), state_store=store)
    case = manager.create_case_from_text("2 pcs Schneider Electric LC1D09BD", title="Persist draft")
    first = QuotationCommercialService(state_store=store)
    first.register_draft(ProposedQuote(
        quote_id="QUOTE-PERSISTED",
        case_id=case.case_id,
        lines=[QuoteLine(line_no=1, requested_mpn="LC1D09BD", quantity="2", unit_price="1.25", source_price_id="CAT-v1-SKU1", match_status="exact")],
    ))

    restored = QuotationCommercialService(state_store=SQLiteStateStore(tmp_path / "quote-state.sqlite3"))
    saved = restored.get_draft("QUOTE-PERSISTED")
    assert saved is not None
    assert saved.lines[0].quantity == Decimal("2")
    assert saved.draft_hash
