"""SQLite persistence for the local RFQ prototype.

This store makes cases, line items, audit events, and the catalog survive process
restarts. It is a single-workspace local/demo store, not a tenant-isolation layer.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


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
                    payload TEXT NOT NULL,
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
                """
            )

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
