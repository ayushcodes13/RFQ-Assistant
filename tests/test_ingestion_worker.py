"""Durability, lease recovery, and local background processing tests."""

import multiprocessing
import threading
import time
from pathlib import Path

import pytest
import time_machine

from rfq_assistant.cases.manager import CaseManager, IngestionLeaseLostError
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.ingestion.worker import RFQIngestionWorker
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.persistence import SQLiteStateStore
from rfq_assistant.schemas.enums import CaseStatus, ProcessingStage, SourceType


def _services(tmp_path):
    store = SQLiteStateStore(tmp_path / "state.sqlite3")
    catalog = CatalogRepository(state_store=store)
    manager = CaseManager(
        catalog=catalog, storage=DocumentStorage(tmp_path / "files"), state_store=store
    )
    return manager, store


def _run_worker_until_parser_blocks(database_path, files_path, parser_entered):
    """Child-process target used to model an abrupt worker-host failure."""
    import rfq_assistant.cases.manager as manager_module

    store = SQLiteStateStore(database_path)
    manager = CaseManager(
        catalog=CatalogRepository(state_store=store),
        storage=DocumentStorage(Path(files_path)),
        state_store=store,
    )
    get_parser = manager_module.get_parser

    class BlockingParser:
        def __init__(self, delegate):
            self.delegate = delegate
            self.cache_profile = delegate.cache_profile
            self.cache_dependencies = delegate.cache_dependencies

        def parse(self, content, filename):
            parser_entered.set()
            while True:
                time.sleep(1)

    def blocked_parser(source_type):
        parser = get_parser(source_type)
        return BlockingParser(parser) if source_type == SourceType.CSV else parser

    manager_module.get_parser = blocked_parser
    worker = RFQIngestionWorker(
        manager,
        store,
        poll_seconds=0.01,
        lease_seconds=60,
        heartbeat_seconds=3600,
        max_concurrent_jobs=1,
    )
    worker.start()
    while True:
        time.sleep(1)


def test_worker_processes_persisted_upload_without_api_request_waiting(tmp_path):
    manager, store = _services(tmp_path)
    content = b"MPN,Manufacturer,Qty\nLC1D09BD,Schneider Electric,2\n"
    pending = manager.enqueue_case_from_upload("request.csv", content)

    assert pending.status == CaseStatus.PROCESSING
    assert pending.processing_stage == ProcessingStage.QUEUED
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
    assert completed.processing_stage == ProcessingStage.READY_FOR_REVIEW
    persisted = next(
        row for row in store.load_cases() if row["case_id"] == pending.case_id
    )
    assert persisted["processing_stage"] == ProcessingStage.READY_FOR_REVIEW.value
    assert len(manager.get_lines(pending.case_id)) == 1
    assert store.get_ingestion_job(pending.case_id)["state"] == "completed"


def test_live_worker_stage_is_saved_while_extraction_is_running(tmp_path, monkeypatch):
    import rfq_assistant.cases.manager as manager_module

    manager, store = _services(tmp_path)
    pending = manager.enqueue_case_from_upload(
        "request.csv", b"MPN,Manufacturer,Qty\nLC1D09BD,Schneider Electric,2\n"
    )
    real_get_parser = manager_module.get_parser
    entered_parser = threading.Event()
    continue_parser = threading.Event()

    class BlockingParser:
        def __init__(self, delegate):
            self.delegate = delegate
            self.cache_profile = delegate.cache_profile
            self.cache_dependencies = delegate.cache_dependencies

        def parse(self, content, filename):
            entered_parser.set()
            assert continue_parser.wait(timeout=3)
            return self.delegate.parse(content, filename)

    monkeypatch.setattr(
        manager_module,
        "get_parser",
        lambda source_type: (
            BlockingParser(real_get_parser(source_type))
            if source_type == SourceType.CSV
            else real_get_parser(source_type)
        ),
    )
    worker = RFQIngestionWorker(
        manager, store, poll_seconds=0.005, lease_seconds=2, heartbeat_seconds=0.1
    )
    worker.start()
    try:
        assert entered_parser.wait(timeout=2)
        assert (
            manager.get_case(pending.case_id).processing_stage
            == ProcessingStage.EXTRACTING
        )
        persisted = next(
            row for row in store.load_cases() if row["case_id"] == pending.case_id
        )
        assert persisted["processing_stage"] == ProcessingStage.EXTRACTING.value
    finally:
        continue_parser.set()
        worker.stop()

    assert (
        manager.get_case(pending.case_id).processing_stage
        == ProcessingStage.READY_FOR_REVIEW
    )


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


def test_killed_worker_process_restarts_and_reclaims_in_flight_case(tmp_path):
    manager, store = _services(tmp_path)
    case = manager.enqueue_case_from_upload(
        "request.csv", b"MPN,Manufacturer,Qty\nLC1D09BD,Schneider Electric,2\n"
    )
    context = multiprocessing.get_context("spawn")
    parser_entered = context.Event()
    child = context.Process(
        target=_run_worker_until_parser_blocks,
        args=(str(store.database_path), str(manager.storage.base_dir), parser_entered),
    )
    child.start()
    restarted_worker = None

    try:
        assert parser_entered.wait(timeout=10), "child worker did not reach extraction"
        in_flight = store.get_ingestion_job(case.case_id)
        assert in_flight["state"] == "processing"
        assert in_flight["attempts"] == 1

        child.kill()
        child.join(timeout=5)
        assert not child.is_alive(), "simulated worker process did not terminate"

        # Expire the abandoned lease directly so recovery does not depend on a
        # wall-clock sleep or a short production lease setting.
        with store._connect() as connection:
            connection.execute(
                "UPDATE ingestion_jobs SET lease_expires_at = ? WHERE job_id = ?",
                (time.time() - 1, in_flight["job_id"]),
            )

        recovered_store = SQLiteStateStore(store.database_path)
        recovered_manager = CaseManager(
            catalog=CatalogRepository(state_store=recovered_store),
            storage=DocumentStorage(manager.storage.base_dir),
            state_store=recovered_store,
        )
        restarted_worker = RFQIngestionWorker(
            recovered_manager,
            recovered_store,
            poll_seconds=0.01,
            lease_seconds=30,
            heartbeat_seconds=0.1,
            max_concurrent_jobs=1,
        )
        restarted_worker.start()

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = recovered_store.get_ingestion_job(case.case_id)
            if job["state"] == "completed":
                break
            time.sleep(0.01)
        else:
            pytest.fail("restarted worker did not finish the reclaimed case")
    finally:
        if restarted_worker is not None:
            restarted_worker.stop()
        if child.is_alive():
            child.kill()
            child.join(timeout=5)

    recovered = recovered_manager.get_case(case.case_id)
    assert recovered.status == CaseStatus.NEEDS_REVIEW
    assert recovered.processing_stage == ProcessingStage.READY_FOR_REVIEW
    assert len(recovered_manager.get_lines(case.case_id)) == 1
    finished = recovered_store.get_ingestion_job(case.case_id)
    assert finished["state"] == "completed"
    assert finished["attempts"] == 2


def test_duplicate_enqueue_for_one_case_keeps_a_single_durable_job(tmp_path):
    manager, store = _services(tmp_path)
    case = manager.create_case_from_upload(
        "request.csv", b"MPN,Qty\nLC1D09BD,2\n", _defer_processing=True
    )

    first_job_id = store.enqueue_ingestion_job(
        case.case_id, case.source_file.sha256_digest
    )
    repeated_job_id = store.enqueue_ingestion_job(
        case.case_id, case.source_file.sha256_digest
    )

    assert repeated_job_id == first_job_id
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
                case_id,
                job_id=job_id,
                worker_id=worker_id,
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
