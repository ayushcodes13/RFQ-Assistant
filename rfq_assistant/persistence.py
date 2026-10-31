"""SQLite persistence for the local RFQ prototype.

This store makes cases, line items, audit events, and the catalog survive process
restarts. It is a single-workspace local/demo store, not a tenant-isolation layer.
"""

import json
import logging
import sqlite3
import time
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

MAX_PROCESSING_ARTIFACT_BYTES = 10 * 1024 * 1024
log = logging.getLogger(__name__)


@runtime_checkable
class StateStore(Protocol):
    """Persistence contract shared by cases, catalog, and ingestion workers.

    Implementations must preserve the transaction and lease-fencing semantics
    used by ``SQLiteStateStore``. This interface is not evidence that the
    current SQLite implementation is safe across hosts.
    """

    def enqueue_ingestion_job(self, case_id: str, source_digest: str) -> str: ...
    def reconcile_processing_cases(self) -> int: ...
    def claim_ingestion_job(
        self, worker_id: str, lease_seconds: float = 90.0, max_attempts: int = 3
    ) -> Optional[Dict[str, Any]]: ...
    def heartbeat_ingestion_job(
        self, job_id: str, worker_id: str, lease_seconds: float = 90.0
    ) -> bool: ...
    def owns_ingestion_job(self, job_id: str, worker_id: str) -> bool: ...
    def finish_ingestion_job(self, job_id: str, worker_id: str) -> bool: ...
    def fail_ingestion_job(
        self, job_id: str, worker_id: str, error_code: str, max_attempts: int = 3
    ) -> str: ...
    def get_ingestion_job(self, case_id: str) -> Optional[Dict[str, Any]]: ...
    def failed_ingestion_case_ids(self) -> List[str]: ...
    def save_case_snapshot_if_job_owned(
        self, case: Any, lines: List[Any], events: List[Any], job_id: str, worker_id: str
    ) -> bool: ...
    def load_case_snapshot(self, case_id: str) -> Optional[Dict[str, Any]]: ...
    def load_cases(self) -> List[Dict[str, Any]]: ...
    def load_lines(self, case_id: str) -> List[Dict[str, Any]]: ...
    def load_audit_events(self, case_id: str) -> List[Dict[str, Any]]: ...
    def save_case_snapshot(self, case: Any, lines: List[Any], events: List[Any]) -> None: ...
    def delete_case(self, case_id: str) -> bool: ...
    def load_processing_artifact(
        self, case_id: str, artifact_name: str, source_digest: str, profile_digest: str
    ) -> Optional[Dict[str, Any]]: ...
    def save_processing_artifact(
        self,
        case_id: str,
        artifact_name: str,
        source_digest: str,
        profile_digest: str,
        payload: Any,
        *,
        job_id: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> bool: ...
    def load_catalog(self) -> List[Dict[str, Any]]: ...
    def replace_catalog(self, items: List[Any]) -> None: ...
    def delete_catalog(self) -> None: ...


class SQLiteStateStore:
    """Small durable state store backed by the Python standard-library SQLite."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS rfq_cases (
                    case_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rfq_lines (
                    case_id TEXT NOT NULL REFERENCES rfq_cases(case_id) ON DELETE CASCADE,
                    line_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    payload BLOB NOT NULL,
                    PRIMARY KEY (case_id, line_id)
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    case_id TEXT NOT NULL REFERENCES rfq_cases(case_id) ON DELETE CASCADE,
                    event_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (case_id, event_id)
                );
                CREATE TABLE IF NOT EXISTS catalog_items (
                    internal_sku TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                    job_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL UNIQUE REFERENCES rfq_cases(case_id) ON DELETE CASCADE,
                    source_digest TEXT NOT NULL,
                    state TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    available_at REAL NOT NULL,
                    worker_id TEXT,
                    heartbeat_at REAL,
                    lease_expires_at REAL,
                    last_error_code TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ingestion_jobs_ready_idx
                    ON ingestion_jobs(state, available_at, created_at);
                CREATE TABLE IF NOT EXISTS processing_artifacts (
                    case_id TEXT NOT NULL REFERENCES rfq_cases(case_id) ON DELETE CASCADE,
                    artifact_name TEXT NOT NULL,
                    source_digest TEXT NOT NULL,
                    profile_digest TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (case_id, artifact_name)
                );
                """
            )

    def _write_case_snapshot(self, connection, case: Any, lines: List[Any], events: List[Any]) -> None:
        connection.execute(
            "INSERT INTO rfq_cases(case_id, payload) VALUES(?, ?) "
            "ON CONFLICT(case_id) DO UPDATE SET payload = excluded.payload",
            (case.case_id, self._dump(case)),
        )
        connection.execute("DELETE FROM rfq_lines WHERE case_id = ?", (case.case_id,))
        connection.execute("DELETE FROM audit_events WHERE case_id = ?", (case.case_id,))
        connection.executemany(
            "INSERT INTO rfq_lines(case_id, line_id, position, payload) VALUES(?, ?, ?, ?)",
            [(case.case_id, line.line_id, index, self._dump(line)) for index, line in enumerate(lines)],
        )
        connection.executemany(
            "INSERT INTO audit_events(case_id, event_id, position, payload) VALUES(?, ?, ?, ?)",
            [(case.case_id, event.event_id, index, self._dump(event)) for index, event in enumerate(events)],
        )

    def enqueue_ingestion_job(self, case_id: str, source_digest: str) -> str:
        """Idempotently queue one processing job for a persisted case."""
        now = time.time()
        job_id = f"ingest-{case_id}"
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO ingestion_jobs "
                "(job_id, case_id, source_digest, state, available_at, created_at, updated_at) "
                "VALUES (?, ?, ?, 'queued', ?, ?, ?)",
                (job_id, case_id, source_digest, now, now, now),
            )
        return job_id

    def reconcile_processing_cases(self) -> int:
        """Repair the crash window between persisting a case and enqueueing it."""
        cases = self.load_cases()
        now = time.time()
        inserted = 0
        with self._connect() as connection:
            for payload in cases:
                if payload.get("status") != "PROCESSING":
                    continue
                source_file = payload.get("source_file") or {}
                digest = source_file.get("sha256_digest")
                case_id = payload.get("case_id")
                if not case_id or not digest:
                    continue
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO ingestion_jobs "
                    "(job_id, case_id, source_digest, state, available_at, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'queued', ?, ?, ?)",
                    (f"ingest-{case_id}", case_id, digest, now, now, now),
                )
                inserted += cursor.rowcount
        return inserted

    def claim_ingestion_job(self, worker_id: str, lease_seconds: float = 90.0, max_attempts: int = 3):
        """Atomically recover expired claims and claim the oldest ready job."""
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE ingestion_jobs SET state='queued', worker_id=NULL, heartbeat_at=NULL, "
                "lease_expires_at=NULL, available_at=?, updated_at=? "
                "WHERE state='processing' AND lease_expires_at <= ? AND attempts < ?",
                (now, now, now, max_attempts),
            )
            connection.execute(
                "UPDATE ingestion_jobs SET state='failed', worker_id=NULL, heartbeat_at=NULL, "
                "lease_expires_at=NULL, last_error_code=COALESCE(last_error_code, 'LEASE_EXPIRED'), updated_at=? "
                "WHERE state='processing' AND lease_expires_at <= ? AND attempts >= ?",
                (now, now, max_attempts),
            )
            row = connection.execute(
                "SELECT job_id, case_id, source_digest, attempts, available_at FROM ingestion_jobs "
                "WHERE state='queued' AND available_at <= ? ORDER BY created_at, job_id LIMIT 1",
                (now,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE ingestion_jobs SET state='processing', attempts=attempts+1, worker_id=?, "
                "heartbeat_at=?, lease_expires_at=?, updated_at=? WHERE job_id=? AND state='queued'",
                (worker_id, now, now + lease_seconds, now, row["job_id"]),
            )
            return {
                "job_id": row["job_id"],
                "case_id": row["case_id"],
                "source_digest": row["source_digest"],
                "attempt": int(row["attempts"]) + 1,
                # Time spent ready in the queue, excluding an intentional
                # retry backoff before the job became claimable again.
                "queue_wait_ms": max(0.0, (now - float(row["available_at"])) * 1000.0),
            }

    def heartbeat_ingestion_job(self, job_id: str, worker_id: str, lease_seconds: float = 90.0) -> bool:
        now = time.time()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE ingestion_jobs SET heartbeat_at=?, lease_expires_at=?, updated_at=? "
                "WHERE job_id=? AND state='processing' AND worker_id=?",
                (now, now + lease_seconds, now, job_id, worker_id),
            )
            return cursor.rowcount == 1

    def owns_ingestion_job(self, job_id: str, worker_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM ingestion_jobs WHERE job_id=? AND state='processing' "
                "AND worker_id=? AND lease_expires_at>?",
                (job_id, worker_id, time.time()),
            ).fetchone()
            return row is not None

    def finish_ingestion_job(self, job_id: str, worker_id: str) -> bool:
        now = time.time()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE ingestion_jobs SET state='completed', worker_id=NULL, heartbeat_at=NULL, "
                "lease_expires_at=NULL, last_error_code=NULL, updated_at=? "
                "WHERE job_id=? AND state='processing' AND worker_id=?",
                (now, job_id, worker_id),
            )
            return cursor.rowcount == 1

    def save_case_snapshot_if_job_owned(
        self, case: Any, lines: List[Any], events: List[Any], job_id: str, worker_id: str
    ) -> bool:
        """Atomically fence a worker's case write by its live job lease."""
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            owner = connection.execute(
                "SELECT 1 FROM ingestion_jobs WHERE job_id=? AND state='processing' "
                "AND worker_id=? AND lease_expires_at>?",
                (job_id, worker_id, now),
            ).fetchone()
            if owner is None:
                return False
            self._write_case_snapshot(connection, case, lines, events)
            return True

    def load_case_snapshot(self, case_id: str):
        """Read one current snapshot for restoring in-memory state after a fenced write loses."""
        with self._connect() as connection:
            case_row = connection.execute(
                "SELECT payload FROM rfq_cases WHERE case_id=?", (case_id,)
            ).fetchone()
            if case_row is None:
                return None
            line_rows = connection.execute(
                "SELECT payload FROM rfq_lines WHERE case_id=? ORDER BY position", (case_id,)
            ).fetchall()
            event_rows = connection.execute(
                "SELECT payload FROM audit_events WHERE case_id=? ORDER BY position", (case_id,)
            ).fetchall()
            return {
                "case": json.loads(case_row["payload"]),
                "lines": [json.loads(row["payload"]) for row in line_rows],
                "events": [json.loads(row["payload"]) for row in event_rows],
            }

    def fail_ingestion_job(self, job_id: str, worker_id: str, error_code: str, max_attempts: int = 3) -> str:
        """Retry unexpected worker failures with bounded exponential backoff."""
        now = time.time()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT attempts FROM ingestion_jobs WHERE job_id=? AND state='processing' AND worker_id=?",
                (job_id, worker_id),
            ).fetchone()
            if row is None:
                return "lost"
            attempts = int(row["attempts"])
            state = "failed" if attempts >= max_attempts else "queued"
            delay = 0.0 if state == "failed" else min(2 ** max(0, attempts - 1), 30)
            connection.execute(
                "UPDATE ingestion_jobs SET state=?, available_at=?, worker_id=NULL, heartbeat_at=NULL, "
                "lease_expires_at=NULL, last_error_code=?, updated_at=? WHERE job_id=? AND worker_id=?",
                (state, now + delay, error_code[:80], now, job_id, worker_id),
            )
            return state

    def get_ingestion_job(self, case_id: str):
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM ingestion_jobs WHERE case_id=?", (case_id,)).fetchone()
            return dict(row) if row is not None else None

    def load_processing_artifact(
        self, case_id: str, artifact_name: str, source_digest: str, profile_digest: str
    ) -> Optional[Dict[str, Any]]:
        """Load a case-scoped derived result only for the exact source/profile key."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM processing_artifacts WHERE case_id=? AND artifact_name=? "
                "AND source_digest=? AND profile_digest=?",
                (case_id, artifact_name, source_digest, profile_digest),
            ).fetchone()
            if row is None:
                return None
            try:
                decoder = zlib.decompressobj()
                raw = decoder.decompress(row["payload"], MAX_PROCESSING_ARTIFACT_BYTES + 1)
                if len(raw) > MAX_PROCESSING_ARTIFACT_BYTES or decoder.unconsumed_tail or not decoder.eof:
                    return None
                return json.loads(raw.decode("utf-8"))
            except (zlib.error, UnicodeDecodeError, json.JSONDecodeError):
                log.warning("[rfq_artifact_cache] outcome=corrupt case_id=%s artifact=%s", case_id, artifact_name)
                return None

    def save_processing_artifact(
        self,
        case_id: str,
        artifact_name: str,
        source_digest: str,
        profile_digest: str,
        payload: Any,
        *,
        job_id: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> bool:
        """Persist derived data, optionally fenced to the current worker lease."""
        now = time.time()
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(raw) > MAX_PROCESSING_ARTIFACT_BYTES:
            log.info("[rfq_artifact_cache] outcome=too_large case_id=%s artifact=%s bytes=%d", case_id, artifact_name, len(raw))
            return False
        serialized = zlib.compress(raw, level=6)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if job_id:
                owner = connection.execute(
                    "SELECT 1 FROM ingestion_jobs WHERE job_id=? AND state='processing' "
                    "AND worker_id=? AND lease_expires_at>?",
                    (job_id, worker_id, now),
                ).fetchone()
                if owner is None:
                    return False
            connection.execute(
                "INSERT INTO processing_artifacts "
                "(case_id, artifact_name, source_digest, profile_digest, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(case_id, artifact_name) DO UPDATE SET "
                "source_digest=excluded.source_digest, profile_digest=excluded.profile_digest, "
                "payload=excluded.payload, created_at=excluded.created_at",
                (case_id, artifact_name, source_digest, profile_digest, serialized, now),
            )
            return True

    def failed_ingestion_case_ids(self) -> List[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT case_id FROM ingestion_jobs WHERE state='failed' ORDER BY updated_at"
            ).fetchall()
            return [row["case_id"] for row in rows]

    @staticmethod
    def _dump(model: Any) -> str:
        return json.dumps(model.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))

    def load_cases(self) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM rfq_cases ORDER BY rowid").fetchall()
            return [json.loads(row["payload"]) for row in rows]

    def load_lines(self, case_id: str) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM rfq_lines WHERE case_id = ? ORDER BY position", (case_id,)
            ).fetchall()
            return [json.loads(row["payload"]) for row in rows]

    def load_audit_events(self, case_id: str) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM audit_events WHERE case_id = ? ORDER BY position", (case_id,)
            ).fetchall()
            return [json.loads(row["payload"]) for row in rows]

    def save_case_snapshot(self, case: Any, lines: List[Any], events: List[Any]) -> None:
        """Atomically replaces a case and its children with the latest validated state."""
        with self._connect() as connection:
            self._write_case_snapshot(connection, case, lines, events)

    def delete_case(self, case_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM rfq_cases WHERE case_id = ?", (case_id,))
            return cursor.rowcount > 0

    def load_catalog(self) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM catalog_items ORDER BY internal_sku").fetchall()
            return [json.loads(row["payload"]) for row in rows]

    def replace_catalog(self, items: List[Any]) -> None:
        """Atomically replaces the item master after the caller validates every row."""
        with self._connect() as connection:
            connection.execute("DELETE FROM catalog_items")
            connection.executemany(
                "INSERT INTO catalog_items(internal_sku, payload) VALUES(?, ?)",
                [(item.internal_sku, self._dump(item)) for item in items],
            )

    def delete_catalog(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM catalog_items")
