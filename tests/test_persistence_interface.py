"""The local persistence backend must implement the service-facing contract."""

from rfq_assistant.persistence import SQLiteStateStore, StateStore


def test_sqlite_state_store_implements_service_contract(tmp_path):
    store = SQLiteStateStore(tmp_path / "state" / "rfq.sqlite3")
    assert isinstance(store, StateStore)
