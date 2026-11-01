"""Distributor updates remain proposals until an explicit, versioned decision."""

from fastapi.testclient import TestClient

from rfq_assistant.ingestion.malware import ClamAVScanner
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.knowledge.catalog_updates import (
    CatalogUpdateError,
    CatalogUpdateService,
)
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.persistence import SQLiteStateStore
from rfq_assistant.schemas.models import CatalogItem


class StaticClient:
    model = "gpt-6-luna"
    deployment_version = "test-fixture"

    def __init__(self, output):
        self.output = output

    def complete(self, *, system: str, user: str) -> str:
        assert "untrusted source excerpts" in system
        return self.output


def isolated_service(tmp_path, client=None):
    store = SQLiteStateStore(tmp_path / "state.sqlite3")
    catalog = CatalogRepository(state_store=store)
    catalog.add_item(
        CatalogItem(
            internal_sku="SKU-EXISTING",
            manufacturer="Siemens",
            manufacturer_part_number="6ES7134-6GD01-0BA1",
            description="Analog input module",
            list_price=42.5,
            currency="USD",
            stock_qty=8,
            catalog_version="seed",
        )
    )
    # Persist the test's starting snapshot through the repository's import path.
    store.replace_catalog(catalog.list_all())
    return CatalogUpdateService(catalog, store, client), catalog, store


def canonical_csv(*rows):
    return (
        "internal_sku,manufacturer,manufacturer_part_number,description,list_price,currency,stock_qty\n"
        + "\n".join(rows)
        + "\n"
    ).encode()


def test_new_catalog_row_is_staged_then_explicitly_accepted(tmp_path):
    service, catalog, store = isolated_service(tmp_path)
    proposals = service.stage(
        content=canonical_csv(
            "SKU-NEW,Phoenix Contact,2900364,Power supply,17.25,USD,4"
        ),
        filename="authorized-items.csv",
        actor="Distributor",
    )
    proposal = proposals[0]
    assert proposal.change_type == "new"
    assert proposal.review_status == "pending"
    assert proposal.source_locator.row_number == 2
    assert proposal.proposed_values["list_price"] == "17.25"
    assert catalog.get_by_sku("SKU-NEW") is None

    accepted = service.review(proposal.proposal_id, actor="Distributor", accept=True)
    assert accepted.review_status == "accepted"
    assert accepted.reviewed_by == "Distributor"
    assert catalog.get_by_sku("SKU-NEW").list_price == 17.25
    assert catalog.get_by_sku("SKU-NEW").catalog_version != "seed"

    restored = CatalogRepository(
        state_store=SQLiteStateStore(tmp_path / "state.sqlite3")
    )
    assert restored.get_by_sku("SKU-NEW").manufacturer_part_number == "2900364"
    assert (
        store.load_catalog_update_proposal(proposal.proposal_id)["review_status"]
        == "accepted"
    )


def test_rejected_change_does_not_mutate_catalog_and_can_be_revised(tmp_path):
    service, catalog, _ = isolated_service(tmp_path)
    proposal = service.stage(
        content=canonical_csv(
            "SKU-EXISTING,Siemens,6ES7134-6GD01-0BA1,Analog input module,42.50,USD,18"
        ),
        filename="stock-update.csv",
        actor="Distributor",
    )[0]
    assert proposal.change_type == "changed"
    assert proposal.changed_fields["stock_qty"] == {"current": 8, "proposed": 18}
    before = catalog.get_by_sku("SKU-EXISTING").model_dump()

    rejected = service.review(
        proposal.proposal_id, actor="Distributor", accept=False, note="Wrong branch"
    )
    assert rejected.review_status == "rejected"
    assert catalog.get_by_sku("SKU-EXISTING").model_dump() == before

    revision = service.stage(
        content=canonical_csv(
            "SKU-EXISTING,Siemens,6ES7134-6GD01-0BA1,Analog input module,42.50,USD,12"
        ),
        filename="correction.csv",
        actor="Distributor",
        revision_of=proposal.proposal_id,
    )[0]
    assert revision.revision_of == proposal.proposal_id
    assert revision.proposed_values["stock_qty"] == 12
    assert catalog.get_by_sku("SKU-EXISTING").stock_qty == 8


def test_incomplete_proposal_cannot_be_accepted(tmp_path):
    service, catalog, _ = isolated_service(tmp_path)
    proposal = service.stage(
        content=canonical_csv(",Phoenix Contact,2900364,,17.25,USD,4"),
        filename="partial.csv",
        actor="Distributor",
    )[0]
    assert proposal.blocking_reasons
    try:
        service.review(proposal.proposal_id, actor="Distributor", accept=True)
    except CatalogUpdateError as exc:
        assert "needs clarification" in str(exc)
    else:
        raise AssertionError("Incomplete proposal should not be accepted")
    assert catalog.get_by_sku("") is None


def test_unstructured_note_uses_schema_and_verbatim_grounding(tmp_path):
    line = "SKU-NEW Siemens 6ES7134-6GD01-0BA1 Analog input module price $42.50 USD stock 18"
    output = (
        '{"proposals":[{"internal_sku":"SKU-NEW","manufacturer":"Siemens",'
        '"manufacturer_part_number":"6ES7134-6GD01-0BA1","description":"Analog input module",'
        '"list_price":42.50,"currency":"USD","stock_qty":18,'
        '"segment_id":"structured-1","evidence_quote":"' + line + '"}]}'
    )
    service, catalog, _ = isolated_service(tmp_path, StaticClient(output))
    proposal = service.stage(
        content=b"", filename="note.txt", actor="Distributor", pasted_text=line
    )[0]
    assert proposal.change_type == "new"
    assert proposal.evidence_quote == line
    assert catalog.get_by_sku("SKU-NEW") is None


def test_unstructured_note_without_luna_is_explicit_and_does_not_change_data(tmp_path):
    service, catalog, _ = isolated_service(tmp_path)
    try:
        service.stage(
            content=b"",
            filename="note.txt",
            actor="Distributor",
            pasted_text="Stock for SKU-EXISTING is now 18",
        )
    except CatalogUpdateError as exc:
        assert "configured GPT-6 Luna" in str(exc)
    else:
        raise AssertionError(
            "Unstructured update should require Luna or a structured CSV"
        )
    assert catalog.get_by_sku("SKU-EXISTING").stock_qty == 8


def test_llm_cannot_propose_a_value_outside_its_verbatim_quote(tmp_path):
    line = "SKU-NEW Siemens 6ES7134-6GD01-0BA1 Analog input module price $42.50 USD stock 18"
    output = (
        '{"proposals":[{"internal_sku":"SKU-NEW","manufacturer":"Made-up maker",'
        '"manufacturer_part_number":"6ES7134-6GD01-0BA1","description":"Analog input module",'
        '"list_price":42.50,"currency":"USD","stock_qty":18,'
        '"segment_id":"structured-1","evidence_quote":"' + line + '"}]}'
    )
    service, catalog, _ = isolated_service(tmp_path, StaticClient(output))
    try:
        service.stage(
            content=b"", filename="note.txt", actor="Distributor", pasted_text=line
        )
    except CatalogUpdateError as exc:
        assert "manufacturer is not verbatim" in str(exc)
    else:
        raise AssertionError("Ungrounded model facts must not be staged")
    assert catalog.get_by_sku("SKU-NEW") is None


def test_catalog_update_api_retains_source_and_rejection_is_audited(
    tmp_path, monkeypatch
):
    import importlib

    api_module = importlib.import_module("rfq_assistant.api.app")
    store = SQLiteStateStore(tmp_path / "api-state.sqlite3")
    catalog = CatalogRepository(state_store=store)
    catalog.add_item(
        CatalogItem(
            internal_sku="SKU-EXISTING",
            manufacturer="Siemens",
            manufacturer_part_number="6ES7134-6GD01-0BA1",
            description="Analog input module",
            stock_qty=8,
            catalog_version="seed",
        )
    )
    service = CatalogUpdateService(catalog, store)
    source_storage = DocumentStorage(tmp_path / "source-storage")
    monkeypatch.setattr(api_module, "catalog_update_service", service)
    monkeypatch.setattr(api_module, "catalog_update_source_storage", source_storage)
    monkeypatch.setattr(
        api_module, "clamav_scanner", ClamAVScanner(protected_mode=False)
    )
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("PILOT_API_KEYS", raising=False)

    csv_bytes = canonical_csv(
        "SKU-EXISTING,Siemens,6ES7134-6GD01-0BA1,Analog input module,,USD,18"
    )
    with TestClient(api_module.app) as client:
        response = client.post(
            "/api/catalogs/updates",
            files={"file": ("authorized-stock.csv", csv_bytes, "text/csv")},
        )
        assert response.status_code == 200, response.text
        proposal = response.json()[0]
        assert catalog.get_by_sku("SKU-EXISTING").stock_qty == 8

        source = client.get(f"/api/catalogs/updates/{proposal['proposal_id']}/source")
        assert source.status_code == 200
        assert source.content == csv_bytes

        rejected = client.post(
            f"/api/catalogs/updates/{proposal['proposal_id']}/reject",
            json={"note": "Wrong warehouse"},
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["review_status"] == "rejected"
        assert rejected.json()["reviewed_by"]
        assert catalog.get_by_sku("SKU-EXISTING").stock_qty == 8
