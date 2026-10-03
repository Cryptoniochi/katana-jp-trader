"""SQLite-backed live-execution journal for Phase 6-B Step 1.

Safety invariant:
- this repository contains no broker adapter or network transport;
- claiming is atomic;
- a claimed/pending/submitted/unknown execution cannot be reclaimed;
- ambiguous submission outcomes are persisted as UNKNOWN and require explicit
  reconciliation outside this repository before any future action.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from app.live.live_execution_journal_models import (
    LiveExecutionJournalRecord,
    LiveExecutionState,
)


class LiveExecutionJournalError(RuntimeError):
    """Base error for live-execution journal persistence."""


class LiveExecutionJournalConflictError(LiveExecutionJournalError):
    """The same execution key is bound to different immutable content."""


class LiveExecutionTransitionError(LiveExecutionJournalError):
    """A requested state transition is not permitted."""


class LiveExecutionAlreadyClaimedError(LiveExecutionTransitionError):
    """The execution has already crossed the PREPARED boundary."""


class SQLiteLiveExecutionJournal:
    """Durable submission-control journal using the KATANA SQLite database."""

    TABLE_NAME = "live_execution_journal"

    _ALLOWED_TRANSITIONS = {
        LiveExecutionState.PREPARED: {
            LiveExecutionState.CLAIMED,
            LiveExecutionState.ABORTED,
        },
        LiveExecutionState.CLAIMED: {
            LiveExecutionState.SUBMISSION_PENDING,
            LiveExecutionState.ABORTED,
            LiveExecutionState.UNKNOWN,
        },
        LiveExecutionState.SUBMISSION_PENDING: {
            LiveExecutionState.SUBMITTED,
            LiveExecutionState.UNKNOWN,
        },
        LiveExecutionState.SUBMITTED: set(),
        LiveExecutionState.ABORTED: set(),
        LiveExecutionState.UNKNOWN: set(),
    }

    def __init__(
        self,
        database_path: Path,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self._initialize()

    def prepare(
        self,
        execution_key: str,
        *,
        order_fingerprint: str,
        order_id: str,
        signal_id: str,
        detail: str | None = None,
    ) -> LiveExecutionJournalRecord:
        """Create PREPARED once; identical repeated preparation is idempotent."""

        key = self._required(execution_key, "execution_key")
        fingerprint = self._required(order_fingerprint, "order_fingerprint")
        normalized_order_id = self._required(order_id, "order_id")
        normalized_signal_id = self._required(signal_id, "signal_id")
        normalized_detail = self._optional(detail)
        now = self._current_time()

        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    f"""
                    INSERT OR IGNORE INTO {self.TABLE_NAME} (
                        execution_key,
                        order_fingerprint,
                        order_id,
                        signal_id,
                        state,
                        created_at,
                        updated_at,
                        detail
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key,
                        fingerprint,
                        normalized_order_id,
                        normalized_signal_id,
                        LiveExecutionState.PREPARED.value,
                        now.isoformat(),
                        now.isoformat(),
                        normalized_detail,
                    ),
                )
                connection.commit()

                if cursor.rowcount == 1:
                    row = self._select_row(connection, key)
                    if row is None:
                        raise LiveExecutionJournalError(
                            f"Prepared execution disappeared: {key}"
                        )
                    return self._row_to_record(row)

                row = self._select_row(connection, key)
        except sqlite3.Error as error:
            raise LiveExecutionJournalError(
                f"Could not prepare live execution: {key}"
            ) from error

        if row is None:
            raise LiveExecutionJournalError(
                f"Execution disappeared after prepare conflict: {key}"
            )

        record = self._row_to_record(row)
        candidate = (
            fingerprint,
            normalized_order_id,
            normalized_signal_id,
        )
        existing = (
            record.order_fingerprint,
            record.order_id,
            record.signal_id,
        )
        if existing != candidate:
            raise LiveExecutionJournalConflictError(
                "Execution key is already bound to different order content: "
                f"{key}"
            )
        return record

    def claim(self, execution_key: str) -> LiveExecutionJournalRecord:
        """Atomically move PREPARED to CLAIMED exactly once."""

        key = self._required(execution_key, "execution_key")
        now = self._current_time()

        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    f"""
                    UPDATE {self.TABLE_NAME}
                    SET
                        state = ?,
                        claimed_at = ?,
                        updated_at = ?
                    WHERE execution_key = ?
                      AND state = ?
                    """,
                    (
                        LiveExecutionState.CLAIMED.value,
                        now.isoformat(),
                        now.isoformat(),
                        key,
                        LiveExecutionState.PREPARED.value,
                    ),
                )

                if cursor.rowcount != 1:
                    row = self._select_row(connection, key)
                    connection.rollback()
                    if row is None:
                        raise LiveExecutionJournalError(
                            f"Live execution does not exist: {key}"
                        )
                    existing = self._row_to_record(row)
                    raise LiveExecutionAlreadyClaimedError(
                        "Live execution cannot be reclaimed from state "
                        f"{existing.state.value}: {key}"
                    )

                row = self._select_row(connection, key)
                connection.commit()
        except (
            LiveExecutionJournalError,
            LiveExecutionAlreadyClaimedError,
        ):
            raise
        except sqlite3.Error as error:
            raise LiveExecutionJournalError(
                f"Could not claim live execution: {key}"
            ) from error

        if row is None:
            raise LiveExecutionJournalError(
                f"Claimed execution disappeared: {key}"
            )
        return self._row_to_record(row)

    def mark_submission_pending(
        self,
        execution_key: str,
        *,
        detail: str | None = None,
    ) -> LiveExecutionJournalRecord:
        """Record the last durable point immediately before future transport."""

        return self._transition(
            execution_key,
            expected=LiveExecutionState.CLAIMED,
            target=LiveExecutionState.SUBMISSION_PENDING,
            timestamp_column="submission_pending_at",
            detail=detail,
        )

    def mark_submitted(
        self,
        execution_key: str,
        *,
        broker_order_id: str,
        detail: str | None = None,
    ) -> LiveExecutionJournalRecord:
        """Record a broker-confirmed submission.

        Phase 6-B Step 1 never calls this from a network transport. Tests and
        future reconciliation code may use it to verify journal semantics.
        """

        normalized_broker_order_id = self._required(
            broker_order_id,
            "broker_order_id",
        )
        return self._transition(
            execution_key,
            expected=LiveExecutionState.SUBMISSION_PENDING,
            target=LiveExecutionState.SUBMITTED,
            timestamp_column="submitted_at",
            broker_order_id=normalized_broker_order_id,
            detail=detail,
        )

    def mark_aborted(
        self,
        execution_key: str,
        *,
        detail: str | None = None,
    ) -> LiveExecutionJournalRecord:
        """Abort only before a submission attempt could have reached broker."""

        key = self._required(execution_key, "execution_key")
        record = self.get_required(key)
        if record.state not in {
            LiveExecutionState.PREPARED,
            LiveExecutionState.CLAIMED,
        }:
            raise LiveExecutionTransitionError(
                "ABORTED is only allowed before SUBMISSION_PENDING: "
                f"{record.state.value} -> aborted"
            )
        return self._transition(
            key,
            expected=record.state,
            target=LiveExecutionState.ABORTED,
            timestamp_column="aborted_at",
            detail=detail,
        )

    def mark_unknown(
        self,
        execution_key: str,
        *,
        detail: str | None = None,
    ) -> LiveExecutionJournalRecord:
        """Freeze an ambiguous attempt so automatic retry cannot occur."""

        key = self._required(execution_key, "execution_key")
        record = self.get_required(key)
        if record.state not in {
            LiveExecutionState.CLAIMED,
            LiveExecutionState.SUBMISSION_PENDING,
        }:
            raise LiveExecutionTransitionError(
                "UNKNOWN is only allowed after claim and before confirmation: "
                f"{record.state.value} -> unknown"
            )
        return self._transition(
            key,
            expected=record.state,
            target=LiveExecutionState.UNKNOWN,
            timestamp_column="unknown_at",
            detail=detail,
        )

    def get(
        self,
        execution_key: str,
    ) -> LiveExecutionJournalRecord | None:
        key = self._required(execution_key, "execution_key")
        try:
            with self._connect() as connection:
                row = self._select_row(connection, key)
        except sqlite3.Error as error:
            raise LiveExecutionJournalError(
                f"Could not read live execution: {key}"
            ) from error
        return None if row is None else self._row_to_record(row)

    def get_required(self, execution_key: str) -> LiveExecutionJournalRecord:
        record = self.get(execution_key)
        if record is None:
            raise LiveExecutionJournalError(
                f"Live execution does not exist: {execution_key.strip()}"
            )
        return record

    def count(self) -> int:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"SELECT COUNT(*) FROM {self.TABLE_NAME}"
                ).fetchone()
        except sqlite3.Error as error:
            raise LiveExecutionJournalError(
                "Could not count live executions."
            ) from error
        return 0 if row is None else int(row[0])

    def _transition(
        self,
        execution_key: str,
        *,
        expected: LiveExecutionState,
        target: LiveExecutionState,
        timestamp_column: str,
        broker_order_id: str | None = None,
        detail: str | None = None,
    ) -> LiveExecutionJournalRecord:
        key = self._required(execution_key, "execution_key")
        if target not in self._ALLOWED_TRANSITIONS[expected]:
            raise LiveExecutionTransitionError(
                f"Illegal live-execution transition: "
                f"{expected.value} -> {target.value}"
            )

        allowed_timestamp_columns = {
            "submission_pending_at",
            "submitted_at",
            "aborted_at",
            "unknown_at",
        }
        if timestamp_column not in allowed_timestamp_columns:
            raise ValueError("Unsupported journal timestamp column.")

        now = self._current_time()
        normalized_detail = self._optional(detail)

        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                assignments = [
                    "state = ?",
                    f"{timestamp_column} = ?",
                    "updated_at = ?",
                ]
                values: list[object] = [
                    target.value,
                    now.isoformat(),
                    now.isoformat(),
                ]
                if broker_order_id is not None:
                    assignments.append("broker_order_id = ?")
                    values.append(broker_order_id)
                if normalized_detail is not None:
                    assignments.append("detail = ?")
                    values.append(normalized_detail)

                values.extend((key, expected.value))
                cursor = connection.execute(
                    f"""
                    UPDATE {self.TABLE_NAME}
                    SET {", ".join(assignments)}
                    WHERE execution_key = ?
                      AND state = ?
                    """,
                    tuple(values),
                )

                if cursor.rowcount != 1:
                    row = self._select_row(connection, key)
                    connection.rollback()
                    if row is None:
                        raise LiveExecutionJournalError(
                            f"Live execution does not exist: {key}"
                        )
                    current = self._row_to_record(row)
                    raise LiveExecutionTransitionError(
                        "Live execution state changed or transition is invalid: "
                        f"expected={expected.value} "
                        f"actual={current.state.value} "
                        f"target={target.value}"
                    )

                row = self._select_row(connection, key)
                connection.commit()
        except (LiveExecutionJournalError, LiveExecutionTransitionError):
            raise
        except sqlite3.Error as error:
            raise LiveExecutionJournalError(
                f"Could not transition live execution: {key}"
            ) from error

        if row is None:
            raise LiveExecutionJournalError(
                f"Transitioned execution disappeared: {key}"
            )
        return self._row_to_record(row)

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._connect() as connection:
                connection.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        execution_key TEXT NOT NULL UNIQUE,
                        order_fingerprint TEXT NOT NULL,
                        order_id TEXT NOT NULL,
                        signal_id TEXT NOT NULL,
                        state TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        claimed_at TEXT,
                        submission_pending_at TEXT,
                        submitted_at TEXT,
                        aborted_at TEXT,
                        unknown_at TEXT,
                        broker_order_id TEXT,
                        detail TEXT,
                        CHECK (
                            state IN (
                                'prepared',
                                'claimed',
                                'submission_pending',
                                'submitted',
                                'aborted',
                                'unknown'
                            )
                        )
                    )
                    """
                )
                connection.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS
                        idx_live_execution_journal_order_id
                    ON {self.TABLE_NAME} (order_id)
                    """
                )
                connection.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS
                        idx_live_execution_journal_signal_id
                    ON {self.TABLE_NAME} (signal_id)
                    """
                )
                connection.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS
                        idx_live_execution_journal_state
                    ON {self.TABLE_NAME} (state)
                    """
                )
                connection.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS
                        idx_live_execution_journal_updated_at
                    ON {self.TABLE_NAME} (updated_at DESC)
                    """
                )
                connection.commit()
        except sqlite3.Error as error:
            raise LiveExecutionJournalError(
                "Could not initialize live-execution journal."
            ) from error

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=30.0,
        )
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @staticmethod
    def _select_row(
        connection: sqlite3.Connection,
        execution_key: str,
    ) -> tuple | None:
        return connection.execute(
            f"""
            SELECT
                execution_key,
                order_fingerprint,
                order_id,
                signal_id,
                state,
                created_at,
                updated_at,
                claimed_at,
                submission_pending_at,
                submitted_at,
                aborted_at,
                unknown_at,
                broker_order_id,
                detail
            FROM {SQLiteLiveExecutionJournal.TABLE_NAME}
            WHERE execution_key = ?
            """,
            (execution_key,),
        ).fetchone()

    @staticmethod
    def _row_to_record(row: tuple) -> LiveExecutionJournalRecord:
        return LiveExecutionJournalRecord(
            execution_key=str(row[0]),
            order_fingerprint=str(row[1]),
            order_id=str(row[2]),
            signal_id=str(row[3]),
            state=LiveExecutionState(str(row[4])),
            created_at=datetime.fromisoformat(str(row[5])),
            updated_at=datetime.fromisoformat(str(row[6])),
            claimed_at=SQLiteLiveExecutionJournal._optional_datetime(row[7]),
            submission_pending_at=(
                SQLiteLiveExecutionJournal._optional_datetime(row[8])
            ),
            submitted_at=SQLiteLiveExecutionJournal._optional_datetime(row[9]),
            aborted_at=SQLiteLiveExecutionJournal._optional_datetime(row[10]),
            unknown_at=SQLiteLiveExecutionJournal._optional_datetime(row[11]),
            broker_order_id=(
                None if row[12] is None else str(row[12])
            ),
            detail=None if row[13] is None else str(row[13]),
        )

    @staticmethod
    def _optional_datetime(value: object) -> datetime | None:
        if value is None:
            return None
        return datetime.fromisoformat(str(value))

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)

    @staticmethod
    def _required(value: str, name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{name} must not be empty.")
        return normalized

    @staticmethod
    def _optional(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None
