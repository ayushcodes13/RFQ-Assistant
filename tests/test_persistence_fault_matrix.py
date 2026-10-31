"""Deterministic failure and lease matrix for SQLite-backed processing state."""

from datetime import timedelta
import zlib

import pytest
import time_machine

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.persistence import SQLiteStateStore


def _services(tmp_path):
    store = SQLiteStateStore(tmp_path / "state" / "rfq.sqlite3")
    manager = CaseManager(
        catalog=CatalogRepository(state_store=store),
        storage=DocumentStorage(tmp_path / "files"),
        state_store=store,
    )
    return manager, store


def _queued(manager, store, name="request.csv"):
    case = manager.enqueue_case_from_upload(name, b"MPN,Qty\nPN-123,2\n")
    return case, store.get_ingestion_job(case.case_id)


def test_lease_ownership_heartbeat_and_completion_are_worker_fenced(tmp_path):
    manager, store = _services(tmp_path)
    case, _ = _queued(manager, store)

    with time_machine.travel("2030-01-01T00:00:00+00:00", tick=False):
        job = store.claim_ingestion_job("worker-a", lease_seconds=30)
        assert job is not None
        assert store.owns_ingestion_job(job["job_id"], "worker-a")
        assert not store.owns_ingestion_job(job["job_id"], "worker-b")
        assert store.heartbeat_ingestion_job(
            job["job_id"], "worker-a", lease_seconds=40
        )
        assert not store.heartbeat_ingestion_job(
            job["job_id"], "worker-b", lease_seconds=40
        )
        assert not store.finish_ingestion_job(job["job_id"], "worker-b")
        assert store.finish_ingestion_job(job["job_id"], "worker-a")
        assert not store.owns_ingestion_job(job["job_id"], "worker-a")
        assert store.get_ingestion_job(case.case_id)["state"] == "completed"


def test_retry_backoff_and_retry_exhaustion_use_controlled_time(tmp_path):
    manager, store = _services(tmp_path)
    case, _ = _queued(manager, store)

    with time_machine.travel("2030-01-01T00:00:00+00:00", tick=False) as clock:
        first = store.claim_ingestion_job("worker", lease_seconds=100)
        assert first is not None
        assert (
            store.fail_ingestion_job(
                first["job_id"], "worker", "synthetic error", max_attempts=3
            )
            == "queued"
        )
        assert store.claim_ingestion_job("worker", lease_seconds=100) is None

        clock.shift(timedelta(seconds=1))
        second = store.claim_ingestion_job("worker", lease_seconds=100)
        assert second is not None and second["attempt"] == 2
        assert (
            store.fail_ingestion_job(
                second["job_id"], "worker", "retry", max_attempts=3
            )
            == "queued"
        )
        assert store.claim_ingestion_job("worker", lease_seconds=100) is None

        clock.shift(timedelta(seconds=2))
        third = store.claim_ingestion_job("worker", lease_seconds=100)
        assert third is not None and third["attempt"] == 3
        assert (
            store.fail_ingestion_job(
                third["job_id"], "worker", "x" * 100, max_attempts=3
            )
            == "failed"
        )
        assert store.failed_ingestion_case_ids() == [case.case_id]
        assert store.get_ingestion_job(case.case_id)["last_error_code"] == "x" * 80


def test_unowned_snapshot_writes_are_rejected_and_owned_snapshots_restore(tmp_path):
    manager, store = _services(tmp_path)
    case, _ = _queued(manager, store)
    job = store.claim_ingestion_job("worker-a", lease_seconds=100)
    assert job is not None
    events = manager.get_audit_trail(case.case_id)

    assert not store.save_case_snapshot_if_job_owned(
        case, [], events, job["job_id"], "worker-b"
    )
    assert store.save_case_snapshot_if_job_owned(
        case, [], events, job["job_id"], "worker-a"
    )
    assert store.load_case_snapshot("missing-case") is None
    snapshot = store.load_case_snapshot(case.case_id)
    assert snapshot["case"]["case_id"] == case.case_id
    assert snapshot["lines"] == []
    assert snapshot["events"]


@pytest.mark.parametrize(
    "stored_payload",
    [
        b"not-zlib",
        zlib.compress(b"\xff"),
        zlib.compress(b"not-json"),
        zlib.compress(b"incomplete")[:-2],
    ],
)
def test_corrupt_cached_artifacts_are_cache_misses(tmp_path, stored_payload):
    manager, store = _services(tmp_path)
    case, _ = _queued(manager, store)
    with store._connect() as connection:
        connection.execute(
            "INSERT INTO processing_artifacts "
            "(case_id,artifact_name,source_digest,profile_digest,payload,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (case.case_id, "corrupt", "source", "profile", stored_payload, 1.0),
        )

    assert (
        store.load_processing_artifact(case.case_id, "corrupt", "source", "profile")
        is None
    )
    assert (
        store.load_processing_artifact(
            case.case_id, "corrupt", "wrong-source", "profile"
        )
        is None
    )


def test_reconciliation_ignores_non_processing_and_incomplete_records(tmp_path):
    manager, store = _services(tmp_path)
    case, _ = _queued(manager, store)
    with store._connect() as connection:
        connection.execute(
            "DELETE FROM ingestion_jobs WHERE case_id=?", (case.case_id,)
        )
        connection.execute(
            "UPDATE rfq_cases SET payload=json_set(payload,'$.status','NEEDS_REVIEW') WHERE case_id=?",
            (case.case_id,),
        )

    assert store.reconcile_processing_cases() == 0
