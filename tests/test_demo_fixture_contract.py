"""Verify that published demonstration inputs exercise the two linked workflows."""

from pathlib import Path

from rfq_assistant.ingestion.parsers import get_parser
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.matching.engine import ExactMatchEngine
from rfq_assistant.persistence import SQLiteStateStore
from rfq_assistant.knowledge.catalog_updates import CatalogUpdateService
from rfq_assistant.schemas.enums import SourceType

ROOT = Path(__file__).resolve().parents[1]


def test_demo_distributor_review_feeds_exact_buyer_matching(tmp_path):
    store = SQLiteStateStore(tmp_path / "state.sqlite3")
    catalog = CatalogRepository(state_store=store)
    service = CatalogUpdateService(catalog, store)
    proposed = service.stage(
        content=(ROOT / "demo-data/distributor-update-demo.csv").read_bytes(),
        filename="distributor-update-demo.csv",
        actor="Demo reviewer",
    )
    assert len(proposed) == 3
    assert {item.proposed_values["internal_sku"] for item in proposed} == {
        "SKU-SCH-001", "SKU-DEMO-OMR-001", "SKU-DEMO-WAGO-001",
    }
    assert catalog.get_by_sku("SKU-DEMO-OMR-001") is None
    changes = [
        {
            "proposal_id": item.proposal_id,
            "expected_version": item.version,
            "decision": "reject" if item.proposed_values["internal_sku"] == "SKU-SCH-001" else "accept",
        }
        for item in proposed
    ]
    service.review_batch(changes, actor="Demo reviewer")
    assert catalog.get_by_sku("SKU-SCH-001") is None
    assert catalog.get_by_sku("SKU-DEMO-OMR-001").currency == "USD"
    assert catalog.get_by_sku("SKU-DEMO-WAGO-001").stock_qty == 42

    parsed = get_parser(SourceType.CSV).parse(
        (ROOT / "demo-data/buyer-two-line-bom-demo.csv").read_bytes(),
        "buyer-two-line-bom-demo.csv",
    )
    assert len(parsed.lines) == 2
    matched = ExactMatchEngine(catalog.snapshot())
    for row in parsed.lines:
        result = matched.match_line(row.requested_mpn, row.requested_manufacturer)
        assert result.match_status.value == "EXACT_MATCH"
        assert row.quantity is not None and row.quantity > 0
