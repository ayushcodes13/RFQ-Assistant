"""Durability, lease recovery, and local background processing tests."""

import time
import threading

import pytest
import time_machine

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.cases.manager import IngestionLeaseLostError
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.ingestion.worker import RFQIngestionWorker
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.persistence import SQLiteStateStore
from rfq_assistant.schemas.enums import CaseStatus


def _services(tmp_path):
    store = SQLiteStateStore(tmp_path / "state.sqlite3")
    catalog = CatalogRepository(state_store=store)
    manager = CaseManager(
        catalog=catalog, storage=DocumentStorage(tmp_path / "files"), state_store=store
    )
    return manager, store


def test_worker_processes_persisted_upload_without_api_request_waiting(tmp_path):
    manager, store = _services(tmp_path)
    content = b"MPN,Manufacturer,Qty\nLC1D09BD,Schneider Electric,2\n"
    pending = manager.enqueue_case_from_upload("request.csv", content)

    assert pending.status == CaseStatus.PROCESSING
    assert manager.get_lines(pending.case_id) == []
    assert manager.storage.get_file(pending.case_id, "request.csv") == content
    assert store.get_ingestion_job(pending.case_id)["state"] == "queued"

    worker = RFQIngestionWorker(
        manager, store, poll_seconds=0.01, lease_seconds=1, heartbeat_seconds=0.1
    )
    worker.start()
    try:
        deadline = time.monotonic() + 3
        while (
            time.monotonic() < deadline
            and manager.get_case(pending.case_id).status == CaseStatus.PROCESSING
        ):
            time.sleep(0.01)
    finally:
        worker.stop()

    completed = manager.get_case(pending.case_id)
    assert completed.status == CaseStatus.NEEDS_REVIEW
    assert len(manager.get_lines(pending.case_id)) == 1
    assert store.get_ingestion_job(pending.case_id)["state"] == "completed"


def test_queue_claim_is_atomic_and_expired_lease_is_recovered(tmp_path):
    manager, store = _services(tmp_path)
    pending = manager.enqueue_case_from_upload("request.csv", b"MPN,Qty\nLC1D09BD,2\n")

    with time_machine.travel("2030-01-01T00:00:00+00:00", tick=False) as clock:
        first = store.claim_ingestion_job("worker-a", lease_seconds=10)
        assert first is not None and first["attempt"] == 1
        assert store.claim_ingestion_job("worker-b", lease_seconds=1) is None
        clock.shift(10.1)

        second = store.claim_ingestion_job("worker-b", lease_seconds=10)
        assert second is not None and second["attempt"] == 2
        assert second["case_id"] == pending.case_id
        assert not store.finish_ingestion_job(first["job_id"], "worker-a")
        assert store.finish_ingestion_job(second["job_id"], "worker-b")


def test_queue_wait_is_reported_for_the_attempt_and_persisted_with_case(tmp_path):
    manager, store = _services(tmp_path)
    with time_machine.travel("2030-01-01T00:00:00+00:00", tick=False) as clock:
        pending = manager.enqueue_case_from_upload(
            "request.csv", b"MPN,Manufacturer,Qty\nLC1D09BD,Schneider Electric,2\n"
        )
        clock.shift(2.5)
        job = store.claim_ingestion_job("worker-a")

        assert job is not None
        assert job["queue_wait_ms"] == pytest.approx(2500)
        completed = manager.process_pending_case(
            pending.case_id,
            job_id=job["job_id"],
            worker_id="worker-a",
            queue_wait_ms=job["queue_wait_ms"],
        )
        assert completed.stage_timings_ms["queue_wait_ms"] == pytest.approx(2500)


def test_startup_reconciles_case_saved_before_queue_insert(tmp_path):
    manager, store = _services(tmp_path)
    case = manager.create_case_from_upload(
        "request.csv", b"MPN,Qty\nLC1D09BD,2\n", _defer_processing=True
    )

    assert store.get_ingestion_job(case.case_id) is None
    assert store.reconcile_processing_cases() == 1
    assert store.reconcile_processing_cases() == 0
    assert store.get_ingestion_job(case.case_id)["state"] == "queued"


def test_expired_worker_cannot_commit_over_new_lease_owner(tmp_path):
    manager, store = _services(tmp_path)
    case = manager.enqueue_case_from_upload(
        "request.csv", b"MPN,Manufacturer,Qty\nLC1D09BD,Schneider Electric,2\n"
    )

    with time_machine.travel("2030-01-01T00:00:00+00:00", tick=False) as clock:
        first = store.claim_ingestion_job("worker-a", lease_seconds=10)
        assert first is not None
        clock.shift(10.1)
        second = store.claim_ingestion_job("worker-b", lease_seconds=50)
        assert second is not None

        with pytest.raises(IngestionLeaseLostError):
            manager.process_pending_case(
                case.case_id, job_id=first["job_id"], worker_id="worker-a"
            )

        assert manager.get_case(case.case_id).status == CaseStatus.PROCESSING
        assert manager.get_lines(case.case_id) == []
        assert store.get_ingestion_job(case.case_id)["worker_id"] == "worker-b"

        completed = manager.process_pending_case(
            case.case_id, job_id=second["job_id"], worker_id="worker-b"
        )
        assert completed.status == CaseStatus.NEEDS_REVIEW
        assert len(manager.get_lines(case.case_id)) == 1
        assert store.finish_ingestion_job(second["job_id"], "worker-b")


def test_worker_processes_distinct_cases_with_bounded_concurrency(tmp_path):
    manager, store = _services(tmp_path)
    cases = [
        manager.enqueue_case_from_upload(
            f"request-{index}.csv", b"MPN,Qty\nLC1D09BD,2\n"
        )
        for index in range(4)
    ]
    original = manager.process_pending_case
    lock = threading.Lock()
    active = 0
    max_active = 0

    def slowed(case_id, *, job_id, worker_id, queue_wait_ms=None):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            time.sleep(0.05)
            return original(
                case_id, job_id=job_id, worker_id=worker_id,
                queue_wait_ms=queue_wait_ms,
            )
        finally:
            with lock:
                active -= 1

    manager.process_pending_case = slowed
    worker = RFQIngestionWorker(
        manager,
        store,
        poll_seconds=0.005,
        lease_seconds=2,
        heartbeat_seconds=0.1,
        max_concurrent_jobs=2,
    )
    worker.start()
    try:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and any(
            manager.get_case(case.case_id).status == CaseStatus.PROCESSING
            for case in cases
        ):
            time.sleep(0.01)
    finally:
        worker.stop()

    assert max_active == 2
    assert all(
        manager.get_case(case.case_id).status == CaseStatus.NEEDS_REVIEW
        for case in cases
    )
