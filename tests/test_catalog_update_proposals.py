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


class EchoGroundedTextClient:
    model = "gpt-6-luna"
    deployment_version = "test-fixture"

    def complete(self, *, system: str, user: str) -> str:
        import json

        payload = json.loads(user)
        excerpt = payload["source_excerpts"][0]
        text = excerpt["text"]
        return json.dumps({"proposals": [{
            "internal_sku": None,
            "manufacturer": "WAGO",
            "manufacturer_part_number": "2002-1201",
            "description": "feed-through terminal block",
            "list_price": 1.80,
            "currency": "USD",
            "stock_qty": 42,
            "segment_id": excerpt["segment_id"],
            "evidence_quote": text,
        }]})


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

    accepted = service.review_batch([{"proposal_id": proposal.proposal_id, "expected_version": proposal.version, "decision": "accept"}], actor="Distributor")[0]
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



def test_review_done_requires_every_pending_decision_and_commits_accepts_together(tmp_path):
    service, catalog, store = isolated_service(tmp_path)
    proposals = service.stage(
        content=canonical_csv(
            "SKU-NEW,Phoenix Contact,2900364,Power supply,17.25,USD,4",
            "SKU-EXISTING,Siemens,6ES7134-6GD01-0BA1,Analog input module,42.50,USD,18",
        ),
        filename="two-record-update.csv",
        actor="Distributor",
    )
    assert len(proposals) == 2
    assert catalog.get_by_sku("SKU-NEW") is None
    assert catalog.get_by_sku("SKU-EXISTING").stock_qty == 8

    partial = [{"proposal_id": proposals[0].proposal_id, "expected_version": proposals[0].version, "decision": "accept"}]
    try:
        service.review_batch(partial, actor="Distributor")
    except CatalogUpdateError as exc:
        assert "Review every pending change" in str(exc)
    else:
        raise AssertionError("Partial review must not commit")
    assert catalog.get_by_sku("SKU-NEW") is None
    assert catalog.get_by_sku("SKU-EXISTING").stock_qty == 8
    assert all(store.load_catalog_update_proposal(p.proposal_id)["review_status"] == "pending" for p in proposals)

    reviewed = service.review_batch([
        {"proposal_id": proposals[0].proposal_id, "expected_version": proposals[0].version, "decision": "accept"},
        {"proposal_id": proposals[1].proposal_id, "expected_version": proposals[1].version, "decision": "reject"},
    ], actor="Distributor")
    status_by_id = {p.proposal_id: p.review_status for p in reviewed}
    assert status_by_id[proposals[0].proposal_id] == "accepted"
    assert status_by_id[proposals[1].proposal_id] == "rejected"
    assert catalog.get_by_sku("SKU-NEW").manufacturer_part_number == "2900364"
    assert catalog.get_by_sku("SKU-EXISTING").stock_qty == 8
    assert all(store.load_catalog_update_proposal(p.proposal_id)["review_status"] != "pending" for p in proposals)



def test_review_done_refuses_proposal_if_active_catalog_changed_after_staging(tmp_path):
    service, catalog, store = isolated_service(tmp_path)
    proposal = service.stage(
        content=canonical_csv(
            "SKU-EXISTING,Siemens,6ES7134-6GD01-0BA1,Analog input module,42.50,USD,18"
        ),
        filename="stock-update.csv",
        actor="Distributor",
    )[0]
    active = catalog.get_by_sku("SKU-EXISTING").model_copy(update={"description": "Live row changed"})
    catalog.upsert_item(active)
    current = catalog.get_by_sku("SKU-EXISTING")
    try:
        service.review_batch([{"proposal_id": proposal.proposal_id, "expected_version": proposal.version, "decision": "accept"}], actor="Distributor")
    except CatalogUpdateError as exc:
        assert "catalog changed after these proposals" in str(exc)
    else:
        raise AssertionError("Stale catalog proposal must not apply")
    assert catalog.get_by_sku("SKU-EXISTING").description == "Live row changed"
    assert catalog.get_by_sku("SKU-EXISTING").stock_qty == 8
    assert store.load_catalog_update_proposal(proposal.proposal_id)["review_status"] == "pending"


def test_freeform_update_keeps_greeting_paragraph_as_groundable_source(tmp_path):
    service, catalog, _ = isolated_service(tmp_path, client=EchoGroundedTextClient())
    source = (
        "Hi, this is the distributor update. Add WAGO 2002-1201, feed-through terminal block, "
        "price 1.80 USD, stock 42."
    )
    proposal = service.stage(
        content=source.encode(),
        filename="pasted-distributor-update.txt",
        actor="Distributor",
    )[0]

    assert proposal.change_type == "new"
    assert proposal.review_status == "pending"
    assert proposal.evidence_quote == source
    assert proposal.source_locator.row_number == 1
    assert not any(item.manufacturer == "WAGO" for item in catalog.list_all())


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

    rejected = service.review_batch([{"proposal_id": proposal.proposal_id, "expected_version": proposal.version, "decision": "reject"}], actor="Distributor", note="Wrong branch")[0]
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


def test_nullable_catalog_values_can_be_cleared_only_after_explicit_acceptance(
    tmp_path,
):
    service, catalog, store = isolated_service(tmp_path)
    proposal = service.stage(
        content=canonical_csv(
            "SKU-EXISTING,Siemens,6ES7134-6GD01-0BA1,Analog input module,,,"
        ),
        filename="manual-catalog-edit-SKU-EXISTING.csv",
        actor="Distributor",
        clear_fields=["list_price", "currency", "stock_qty"],
    )[0]

    assert proposal.review_status == "pending"
    assert proposal.clear_fields == ["list_price", "currency", "stock_qty"]
    assert proposal.proposed_values["list_price"] is None
    assert proposal.proposed_values["currency"] is None
    assert proposal.proposed_values["stock_qty"] is None
    assert catalog.get_by_sku("SKU-EXISTING").list_price == 42.5
    assert catalog.get_by_sku("SKU-EXISTING").currency == "USD"
    assert catalog.get_by_sku("SKU-EXISTING").stock_qty == 8

    accepted = service.review_batch([{"proposal_id": proposal.proposal_id, "expected_version": proposal.version, "decision": "accept"}], actor="Distributor")[0]

    active = catalog.get_by_sku("SKU-EXISTING")
    assert accepted.review_status == "accepted"
    assert accepted.reviewed_by == "Distributor"
    assert active.list_price is None
    assert active.currency is None
    assert active.stock_qty is None
    assert active.description == "Analog input module"
    assert store.load_catalog_update_proposal(proposal.proposal_id)["clear_fields"] == [
        "list_price",
        "currency",
        "stock_qty",
    ]


def test_clear_proposal_requires_existing_unique_item_and_nullable_fields(tmp_path):
    service, catalog, _ = isolated_service(tmp_path)
    for fields, csv, filename, message in [
        (
            ["description"],
            "SKU-EXISTING,Siemens,6ES7134-6GD01-0BA1,Analog input module,42.50,USD,8",
            "manual.csv",
            "Only list price, currency, and stock can be cleared",
        ),
        (
            ["list_price"],
            "SKU-EXISTING,Siemens,6ES7134-6GD01-0BA1,Analog input module,,,",
            "manual.csv",
            "Clear price and currency together",
        ),
        (
            ["stock_qty"],
            "SKU-NEW,Siemens,6ES7134-6GD01-0BA2,New module,,,",
            "manual.csv",
            "uniquely matched existing catalog item",
        ),
        (
            ["list_price"],
            "SKU-EXISTING,Siemens,6ES7134-6GD01-0BA1,Analog input module,42.50,USD,8\n"
            "SKU-NEW,Siemens,6ES7134-6GD01-0BA2,New module,1.00,USD,2",
            "manual.csv",
            "one structured catalog item at a time",
        ),
        (
            ["stock_qty", "stock_qty"],
            "SKU-EXISTING,Siemens,6ES7134-6GD01-0BA1,Analog input module,42.50,USD,",
            "manual.csv",
            "Only list price, currency, and stock can be cleared",
        ),
    ]:
        try:
            service.stage(
                content=canonical_csv(csv),
                filename=filename,
                actor="Distributor",
                clear_fields=fields,
            )
        except CatalogUpdateError as exc:
            assert message in str(exc)
        else:
            raise AssertionError("Unsafe clear proposal should be rejected")

    assert catalog.get_by_sku("SKU-EXISTING").list_price == 42.5


def test_clear_fields_cannot_be_inferred_from_unstructured_or_multirow_input(tmp_path):
    service, catalog, _ = isolated_service(tmp_path)
    try:
        service.stage(
            content=b"",
            filename="note.txt",
            actor="Distributor",
            pasted_text="Remove the price from SKU-EXISTING",
            clear_fields=["list_price", "currency"],
        )
    except CatalogUpdateError as exc:
        assert "one structured catalog item" in str(exc)
    else:
        raise AssertionError("Unstructured clear request must not be staged")
    assert catalog.get_by_sku("SKU-EXISTING").list_price == 42.5


def test_clear_fields_must_refer_to_populated_nullable_values(tmp_path):
    service, catalog, _ = isolated_service(tmp_path)
    item = catalog.get_by_sku("SKU-EXISTING")
    item.stock_qty = None
    catalog.upsert_item(item)
    try:
        service.stage(
            content=canonical_csv(
                "SKU-EXISTING,Siemens,6ES7134-6GD01-0BA1,Analog input module,42.50,USD,"
            ),
            filename="manual-catalog-edit-SKU-EXISTING.csv",
            actor="Distributor",
            clear_fields=["stock_qty"],
        )
    except CatalogUpdateError as exc:
        assert "already empty: stock qty" in str(exc)
    else:
        raise AssertionError("An already-empty value must not create a clear proposal")


def test_catalog_update_api_stages_an_explicit_clear_without_applying_it(
    tmp_path, monkeypatch
):
    import importlib

    api_module = importlib.import_module("rfq_assistant.api.app")
    store = SQLiteStateStore(tmp_path / "api-clear-state.sqlite3")
    catalog = CatalogRepository(state_store=store)
    item = CatalogItem(
        internal_sku="SKU-CLEAR",
        manufacturer="Siemens",
        manufacturer_part_number="6ES7134-6GD01-0BA1",
        description="Analog input module",
        list_price=42.5,
        currency="USD",
        stock_qty=8,
        catalog_version="seed",
    )
    catalog.add_item(item)
    store.replace_catalog(catalog.list_all())
    service = CatalogUpdateService(catalog, store)
    monkeypatch.setattr(api_module, "catalog_update_service", service)
    monkeypatch.setattr(
        api_module,
        "catalog_update_source_storage",
        DocumentStorage(tmp_path / "clear-source"),
    )
    monkeypatch.setattr(
        api_module, "clamav_scanner", ClamAVScanner(protected_mode=False)
    )
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("PILOT_API_KEYS", raising=False)
    content = canonical_csv(
        "SKU-CLEAR,Siemens,6ES7134-6GD01-0BA1,Analog input module,,,"
    )

    with TestClient(api_module.app) as client:
        response = client.post(
            "/api/catalogs/updates",
            files={"file": ("manual-catalog-edit-SKU-CLEAR.csv", content, "text/csv")},
            data={"clear_fields": "list_price,currency,stock_qty"},
        )
        assert response.status_code == 200, response.text
        proposal = response.json()[0]
        assert proposal["clear_fields"] == ["list_price", "currency", "stock_qty"]
        assert catalog.get_by_sku("SKU-CLEAR").list_price == 42.5

        accepted = client.post(
            "/api/catalogs/updates/review", json={"decisions": [{"proposal_id": proposal["proposal_id"], "expected_version": proposal["version"], "decision": "accept"}]}
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()[0]["review_status"] == "accepted"
        active = catalog.get_by_sku("SKU-CLEAR")
        assert active.list_price is None
        assert active.currency is None
        assert active.stock_qty is None


def test_incomplete_proposal_cannot_be_accepted(tmp_path):
    service, catalog, _ = isolated_service(tmp_path)
    proposal = service.stage(
        content=canonical_csv(",Phoenix Contact,2900364,,17.25,USD,4"),
        filename="partial.csv",
        actor="Distributor",
    )[0]
    assert proposal.blocking_reasons
    try:
        service.review_batch([{"proposal_id": proposal.proposal_id, "expected_version": proposal.version, "decision": "accept"}], actor="Distributor")[0]
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
        assert "GPT-6 Luna" in str(exc)
        assert "Nothing was changed" in str(exc)
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
            "/api/catalogs/updates/review",
            json={"note": "Wrong warehouse", "decisions": [{"proposal_id": proposal["proposal_id"], "expected_version": proposal["version"], "decision": "reject"}]},
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()[0]["review_status"] == "rejected"
        assert rejected.json()[0]["reviewed_by"]
        assert catalog.get_by_sku("SKU-EXISTING").stock_qty == 8

class PartialRevisionClient:
    """Only emits values grounded in the new correction, not old proposal data."""
    def __init__(self, fields):
        self.fields = fields
        self.last_context = None

    def complete(self, *, system: str, user: str) -> str:
        import json
        payload = json.loads(user)
        self.last_context = payload.get("revision_context")
        segment = payload["source_excerpts"][0]
        return json.dumps({"proposals": [{
            **self.fields,
            "segment_id": segment["segment_id"],
            "evidence_quote": segment["text"],
        }]})


def test_short_rejected_stock_revision_retains_identity_and_original_provenance(tmp_path):
    model = PartialRevisionClient({"stock_qty": 12})
    service, catalog, _ = isolated_service(tmp_path, client=model)
    original = service.stage(
        content=canonical_csv(
            "SKU-EXISTING,Siemens,6ES7134-6GD01-0BA1,Analog input module,42.50,USD,18"
        ), filename="old-stock.csv", actor="Distributor",
    )[0]
    service.review_batch([{
        "proposal_id": original.proposal_id, "expected_version": original.version,
        "decision": "reject",
    }], actor="Distributor")
    correction = service.stage(
        content=b"Stock is 12, not 18.", filename="correction.txt",
        actor="Distributor", revision_of=original.proposal_id,
    )[0]
    assert model.last_context["proposal_id"] == original.proposal_id
    assert correction.revision_of == original.proposal_id
    assert correction.evidence_quote == "Stock is 12, not 18."
    assert correction.proposed_values["internal_sku"] == "SKU-EXISTING"
    assert correction.proposed_values["manufacturer"] == "Siemens"
    assert correction.proposed_values["manufacturer_part_number"] == "6ES7134-6GD01-0BA1"
    assert correction.proposed_values["stock_qty"] == 12
    assert any(original.proposal_id in warning for warning in correction.source_warnings)
    assert catalog.get_by_sku("SKU-EXISTING").stock_qty == 8

    service.review_batch([{
        "proposal_id": correction.proposal_id, "expected_version": correction.version,
        "decision": "accept",
    }], actor="Distributor")
    assert catalog.get_by_sku("SKU-EXISTING").stock_qty == 12


def test_rejected_new_item_can_be_completed_by_one_grounded_sku_correction(tmp_path):
    model = PartialRevisionClient({"internal_sku": "SKU-FIXED"})
    service, catalog, _ = isolated_service(tmp_path, client=model)
    import json

    class MissingSkuClient:
        def complete(self, *, system: str, user: str) -> str:
            segment = json.loads(user)["source_excerpts"][0]
            return json.dumps({"proposals": [{
                "manufacturer": "WAGO",
                "manufacturer_part_number": "2002-1201",
                "description": "feed through terminal",
                "stock_qty": 8,
                "segment_id": segment["segment_id"],
                "evidence_quote": segment["text"],
            }]})

    service.client = MissingSkuClient()
    original = service.stage(
        content=b"WAGO 2002-1201 feed through terminal, stock 8.",
        filename="stock-note.txt", actor="Distributor",
    )[0]
    assert original.blocking_reasons
    service.review_batch([{
        "proposal_id": original.proposal_id, "expected_version": original.version,
        "decision": "reject",
    }], actor="Distributor")
    service.client = model
    correction = service.stage(
        content=b"Internal SKU is SKU-FIXED.", filename="sku-note.txt",
        actor="Distributor", revision_of=original.proposal_id,
    )[0]
    assert correction.proposed_values["internal_sku"] == "SKU-FIXED"
    assert correction.proposed_values["manufacturer"] == "WAGO"
    assert correction.proposed_values["stock_qty"] == 8
    assert not correction.blocking_reasons
    assert catalog.get_by_sku("SKU-FIXED") is None


def test_rejected_proposal_revision_refuses_conflicting_manufacturer(tmp_path):
    model = PartialRevisionClient({"manufacturer": "Schneider Electric", "stock_qty": 12})
    service, catalog, _ = isolated_service(tmp_path, client=model)
    original = service.stage(
        content=canonical_csv(
            "SKU-EXISTING,Siemens,6ES7134-6GD01-0BA1,Analog input module,42.50,USD,18"
        ), filename="old.csv", actor="Distributor",
    )[0]
    service.review_batch([{
        "proposal_id": original.proposal_id, "expected_version": original.version,
        "decision": "reject",
    }], actor="Distributor")
    import pytest
    with pytest.raises(CatalogUpdateError, match="changes the item's identity"):
        service.stage(
            content=b"Schneider Electric stock 12", filename="revision.txt",
            actor="Distributor", revision_of=original.proposal_id,
        )
    assert catalog.get_by_sku("SKU-EXISTING").stock_qty == 8


def test_revision_is_only_allowed_after_proposal_rejection(tmp_path):
    service, _, _ = isolated_service(tmp_path)
    proposal = service.stage(
        content=canonical_csv(
            "SKU-EXISTING,Siemens,6ES7134-6GD01-0BA1,Analog input module,42.50,USD,18"
        ), filename="old.csv", actor="Distributor",
    )[0]
    import pytest
    with pytest.raises(CatalogUpdateError, match="Only a rejected proposal"):
        service.stage(
            content=canonical_csv(
                "SKU-EXISTING,Siemens,6ES7134-6GD01-0BA1,Analog input module,42.50,USD,12"
            ), filename="new.csv", actor="Distributor",
            revision_of=proposal.proposal_id,
        )
