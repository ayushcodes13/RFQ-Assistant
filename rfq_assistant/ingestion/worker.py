"""Durable local worker for expensive RFQ parsing, OCR, and model fallback."""

from __future__ import annotations

import logging
import threading
import time
import uuid

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.persistence import StateStore

log = logging.getLogger(__name__)


class RFQIngestionWorker:
    """Claims SQLite jobs with renewable leases and bounded retries.

    SQLite is appropriate for the single-host prototype. Multi-host production
    deployments should use a shared queue/store with equivalent lease semantics.
    """

    def __init__(
        self,
        manager: CaseManager,
        state_store: StateStore,
        *,
        poll_seconds: float = 0.5,
        lease_seconds: float = 90.0,
        heartbeat_seconds: float = 15.0,
        max_attempts: int = 3,
        max_concurrent_jobs: int = 2,
    ):
        self.manager = manager
        self.state_store = state_store
        self.poll_seconds = poll_seconds
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.max_attempts = max_attempts
        self.max_concurrent_jobs = max(1, max_concurrent_jobs)
        self.worker_id = f"rfq-worker-{uuid.uuid4().hex[:10]}"
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if any(thread.is_alive() for thread in self._threads):
            return
        self.state_store.reconcile_processing_cases()
        for case_id in self.state_store.failed_ingestion_case_ids():
            self.manager.mark_case_processing_failed(case_id)
        self._stop.clear()
        self._threads = [
            threading.Thread(
                target=self._run,
                args=(index,),
                name=f"{self.worker_id}-{index + 1}",
                daemon=True,
            )
            for index in range(self.max_concurrent_jobs)
        ]
        for thread in self._threads:
            thread.start()

    def stop(self, timeout_seconds: float = 10.0) -> None:
        self._stop.set()
        deadline = time.monotonic() + timeout_seconds
        for thread in self._threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))

    def _run(self, index: int = 0) -> None:
        worker_id = f"{self.worker_id}-{index + 1}"
        while not self._stop.is_set():
            job = self.state_store.claim_ingestion_job(
                worker_id, lease_seconds=self.lease_seconds, max_attempts=self.max_attempts
            )
            if job is None:
                for case_id in self.state_store.failed_ingestion_case_ids():
                    self.manager.mark_case_processing_failed(case_id)
                self._stop.wait(self.poll_seconds)
                continue
            self._run_job(job, worker_id)

    def _run_job(self, job: dict, worker_id: str) -> None:
        heartbeat_stop = threading.Event()
        lost_lease = threading.Event()

        def heartbeat() -> None:
            while not heartbeat_stop.wait(self.heartbeat_seconds):
                if not self.state_store.heartbeat_ingestion_job(
                    job["job_id"], worker_id, lease_seconds=self.lease_seconds
                ):
                    lost_lease.set()
                    return

        heartbeat_thread = threading.Thread(
            target=heartbeat, name=f"heartbeat-{job['job_id']}", daemon=True
        )
        heartbeat_thread.start()
        try:
            self.manager.process_pending_case(
                job["case_id"], job_id=job["job_id"], worker_id=worker_id,
                queue_wait_ms=job.get("queue_wait_ms", 0.0),
            )
            if not lost_lease.is_set():
                self.state_store.finish_ingestion_job(job["job_id"], worker_id)
        except Exception as exc:  # noqa: BLE001 - retry policy is centralized here
            result = self.state_store.fail_ingestion_job(
                job["job_id"], worker_id, type(exc).__name__, max_attempts=self.max_attempts
            )
            log.warning(
                "[rfq_worker] case_id=%s attempt=%d outcome=%s error=%s",
                job["case_id"], job["attempt"], result, type(exc).__name__,
            )
            if result == "failed":
                self.manager.mark_case_processing_failed(job["case_id"])
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2.0)
