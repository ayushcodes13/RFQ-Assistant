"""Regression: stock-only catalog updates must not become price citations."""

import importlib
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from rfq_assistant.agents.tools import QuotationCommercialService
from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.quotation.proposal import source_excerpt_supports_price
from rfq_assistant.schemas.enums import ReviewDecision
from rfq_assistant.schemas.models import CatalogItem, RFQLineItemUpdate, SourceLocator


class EchoQuoteEvidence:
    model = "gpt-6-luna"

    def complete(self, *, system: str, user: str) -> str:
        assert "evidence map" in system
        payload = json.loads(user)
        return json.dumps({
            "lines": [
                {
                    "line_no": buyer["line_no"],
                    "buyer_source_id": buyer["source_id"],
                    "buyer_evidence": buyer["text"],
                    "distributor_source_id": distributor["source_id"],
                    "distributor_evidence": distributor["evidence_text"],
                }
                for buyer, distributor in zip(
                    payload["buyer_lines"], payload["retrieved_distributor_records"], strict=True
                )
            ]
        })


@pytest.mark.parametrize(
    ("source_text", "expected_support"),
    [
        ("Stock for LC1D09BD changed to 19", False),
        ("Price for LC1D09BD changed to 42.5 USD", True),
        ("LC1D09BD list price 142.5 USD", False),
        ("LC1D09BD list price 42.5 EUR", False),
    ],
)
def test_accepted_update_must_support_price_and_currency(source_text, expected_support):
    assert source_excerpt_supports_price(source_text, Decimal("42.5"), "USD") is expected_support


@pytest.mark.parametrize(
    ("update_evidence", "expected_source_id"),
    [
        ("LC1D09BD stock is now 19 units", "CAT-synthetic-v1-SKU-SYN"),
        ("LC1D09BD price is 42.5 USD; stock is now 19 units", "CATUP-SYNTH-UPDATE"),
    ],
)
def test_quote_uses_price_citation_only_when_accepted_update_supports_price(
    tmp_path, monkeypatch, update_evidence, expected_source_id,
):
    api = importlib.import_module("rfq_assistant.api.app")
    catalog = CatalogRepository()
    catalog.add_item(CatalogItem(
        internal_sku="SKU-SYN",
        manufacturer="Schneider Electric",
        manufacturer_part_number="LC1D09BD",
        description="Synthetic contactor",
        list_price=42.5,
        currency="USD",
        stock_qty=20,
        catalog_version="synthetic-v1",
    ))
    manager = CaseManager(catalog=catalog, storage=DocumentStorage(tmp_path / "files"))
    case = manager.create_case_from_text(
        "10 pcs Schneider Electric LC1D09BD", title="Catalog citation regression"
    )
    line = manager.get_lines(case.case_id)[0]
    manager.update_line(case.case_id, line.line_id, RFQLineItemUpdate(
        expected_version=line.version,
        review_decision=ReviewDecision.APPROVED,
        actor="Synthetic reviewer",
    ))
    # Only the second stage calls the mock; source parsing remains deterministic.
    manager.llm_extractor = SimpleNamespace(client=EchoQuoteEvidence())
    accepted = SimpleNamespace(
        review_status="accepted",
        current_item=catalog.get_by_sku("SKU-SYN"),
        evidence_quote=update_evidence,
        proposal_id="SYNTH-UPDATE",
        source_locator=SourceLocator(
            file_name="synthetic-catalog-update.txt",
            row_number=1,
            text_snippet=update_evidence,
        ),
    )
    monkeypatch.setattr(api, "catalog_repo", catalog)
    monkeypatch.setattr(api, "case_manager", manager)
    monkeypatch.setattr(api, "commercial_service", QuotationCommercialService())
    monkeypatch.setattr(api, "catalog_update_service", SimpleNamespace(
        list_proposals=lambda: [accepted],
    ))
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("PILOT_API_KEYS", raising=False)

    response = TestClient(api.app).post(f"/v1/rfqs/{case.case_id}/draft-quote")
    assert response.status_code == 200, response.text
    quote = response.json()
    assert quote["quote_proposal_status"] == "grounded", quote
    assert Decimal(quote["total_amount"]) == Decimal("425")
    line_sources = quote["lines"][0]["sources"]
    assert len(line_sources) == 2
    assert line_sources[1]["file_id"] == expected_source_id
    assert "42.5" in line_sources[1]["text_excerpt"]
