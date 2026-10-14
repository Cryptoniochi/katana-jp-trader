"""Durable journal for live broker cancellation attempts.

A broker cancellation is an irreversible network action.  Once an attempt enters
CANCEL_PENDING, a process restart must not silently turn it into a second cancel.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import sqlite3
from pathlib import Path


class LiveCancelJournalState(StrEnum):
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LiveCancelJournalRecord:
    broker_order_id: str
    state: LiveCancelJournalState
    created_at: str
    updated_at: str
    message: str | None


class SQLiteLiveCancelJournalRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS live_cancel_journal (
                    broker_order_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    message TEXT
                )
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def get(self, broker_order_id: str) -> LiveCancelJournalRecord | None:
        oid = broker_order_id.strip()
        if not oid:
            raise ValueError("broker_order_id is required")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT broker_order_id,state,created_at,updated_at,message "
                "FROM live_cancel_journal WHERE broker_order_id=?",
                (oid,),
            ).fetchone()
        return self._record(row) if row is not None else None

    def begin_once(self, broker_order_id: str) -> tuple[LiveCancelJournalRecord, bool]:
        oid = broker_order_id.strip()
        if not oid:
            raise ValueError("broker_order_id is required")
        now = self._now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO live_cancel_journal
                (broker_order_id,state,created_at,updated_at,message)
                VALUES (?,?,?,?,NULL)
                """,
                (oid, LiveCancelJournalState.CANCEL_PENDING.value, now, now),
            )
            row = connection.execute(
                "SELECT broker_order_id,state,created_at,updated_at,message "
                "FROM live_cancel_journal WHERE broker_order_id=?",
                (oid,),
            ).fetchone()
        assert row is not None
        return self._record(row), cursor.rowcount == 1

    def mark_cancelled(self, broker_order_id: str, message: str | None = None) -> LiveCancelJournalRecord:
        return self._transition(
            broker_order_id,
            expected=LiveCancelJournalState.CANCEL_PENDING,
            target=LiveCancelJournalState.CANCELLED,
            message=message,
        )

    def mark_unknown(self, broker_order_id: str, message: str | None = None) -> LiveCancelJournalRecord:
        return self._transition(
            broker_order_id,
            expected=LiveCancelJournalState.CANCEL_PENDING,
            target=LiveCancelJournalState.UNKNOWN,
            message=message,
        )

    def recover_cancelled(
        self,
        broker_order_id: str,
        message: str | None = None,
    ) -> LiveCancelJournalRecord:
        """Promote an ambiguous durable attempt after read-only broker proof.

        This transition is intentionally limited to CANCEL_PENDING/UNKNOWN and
        performs no broker action.  It exists so a restart after a timeout can
        recover without ever re-sending cancelorder.
        """
        oid = broker_order_id.strip()
        if not oid:
            raise ValueError("broker_order_id is required")
        now = self._now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE live_cancel_journal
                SET state=?, updated_at=?, message=?
                WHERE broker_order_id=?
                  AND state IN (?,?)
                """,
                (
                    LiveCancelJournalState.CANCELLED.value,
                    now,
                    message,
                    oid,
                    LiveCancelJournalState.CANCEL_PENDING.value,
                    LiveCancelJournalState.UNKNOWN.value,
                ),
            )
            if cursor.rowcount != 1:
                row = connection.execute(
                    "SELECT state FROM live_cancel_journal WHERE broker_order_id=?",
                    (oid,),
                ).fetchone()
                current = None if row is None else row["state"]
                raise RuntimeError(
                    f"invalid live cancel recovery: {oid} "
                    f"{current!r} -> {LiveCancelJournalState.CANCELLED.value!r}"
                )
            row = connection.execute(
                "SELECT broker_order_id,state,created_at,updated_at,message "
                "FROM live_cancel_journal WHERE broker_order_id=?",
                (oid,),
            ).fetchone()
        assert row is not None
        return self._record(row)

    def _transition(
        self,
        broker_order_id: str,
        *,
        expected: LiveCancelJournalState,
        target: LiveCancelJournalState,
        message: str | None,
    ) -> LiveCancelJournalRecord:
        oid = broker_order_id.strip()
        now = self._now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE live_cancel_journal
                SET state=?, updated_at=?, message=?
                WHERE broker_order_id=? AND state=?
                """,
                (target.value, now, message, oid, expected.value),
            )
            if cursor.rowcount != 1:
                row = connection.execute(
                    "SELECT state FROM live_cancel_journal WHERE broker_order_id=?",
                    (oid,),
                ).fetchone()
                current = None if row is None else row["state"]
                raise RuntimeError(
                    f"invalid live cancel journal transition: "
                    f"{oid} {current!r} -> {target.value!r}"
                )
            row = connection.execute(
                "SELECT broker_order_id,state,created_at,updated_at,message "
                "FROM live_cancel_journal WHERE broker_order_id=?",
                (oid,),
            ).fetchone()
        assert row is not None
        return self._record(row)

    @staticmethod
    def _record(row: sqlite3.Row) -> LiveCancelJournalRecord:
        return LiveCancelJournalRecord(
            broker_order_id=str(row["broker_order_id"]),
            state=LiveCancelJournalState(str(row["state"])),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            message=None if row["message"] is None else str(row["message"]),
        )
