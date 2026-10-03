"""SQLite-backed live-order idempotency reservations for Phase 6-A."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class LiveOrderIdempotencyRepositoryError(RuntimeError):
    """Base error for live-order idempotency persistence."""


class LiveOrderIdempotencyConflictError(LiveOrderIdempotencyRepositoryError):
    """The same idempotency key was used for different order content."""


@dataclass(frozen=True, slots=True)
class LiveOrderIdempotencyReservation:
    idempotency_key: str
    order_fingerprint: str
    order_id: str
    signal_id: str
    reserved_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "idempotency_key",
            "order_fingerprint",
            "order_id",
            "signal_id",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty.")
        if self.reserved_at.tzinfo is None:
            raise ValueError("reserved_at must be timezone-aware.")


class SQLiteLiveOrderIdempotencyStore:
    """Durable and atomic reservation store.

    The table is self-initializing in Phase 6-A so the locked live-order
    foundation does not require changing KATANA's central schema version yet.
    """

    TABLE_NAME = "live_order_idempotency_reservations"

    def __init__(
        self,
        database_path: Path,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = database_path
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self._initialize()

    def reserve(
        self,
        idempotency_key: str,
        *,
        order_fingerprint: str | None = None,
        order_id: str | None = None,
        signal_id: str | None = None,
    ) -> bool:
        """Atomically reserve a key.

        True means newly reserved.
        False means the identical reservation already exists.
        A reused key with different immutable order content raises conflict.
        """

        key = self._required(idempotency_key, "idempotency_key")
        fingerprint = self._required(
            order_fingerprint if order_fingerprint is not None else key,
            "order_fingerprint",
        )
        normalized_order_id = self._required(
            order_id if order_id is not None else key,
            "order_id",
        )
        normalized_signal_id = self._required(
            signal_id if signal_id is not None else key,
            "signal_id",
        )
        reserved_at = self._current_time()

        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    f"""
                    INSERT OR IGNORE INTO {self.TABLE_NAME} (
                        idempotency_key,
                        order_fingerprint,
                        order_id,
                        signal_id,
                        reserved_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        key,
                        fingerprint,
                        normalized_order_id,
                        normalized_signal_id,
                        reserved_at.isoformat(),
                    ),
                )
                connection.commit()

                if cursor.rowcount == 1:
                    return True

                row = connection.execute(
                    f"""
                    SELECT
                        order_fingerprint,
                        order_id,
                        signal_id
                    FROM {self.TABLE_NAME}
                    WHERE idempotency_key = ?
                    """,
                    (key,),
                ).fetchone()

        except sqlite3.Error as error:
            raise LiveOrderIdempotencyRepositoryError(
                f"Could not reserve live-order idempotency key: {key}"
            ) from error

        if row is None:
            raise LiveOrderIdempotencyRepositoryError(
                f"Reservation disappeared after conflict: {key}"
            )

        existing = (str(row[0]), str(row[1]), str(row[2]))
        candidate = (
            fingerprint,
            normalized_order_id,
            normalized_signal_id,
        )
        if existing != candidate:
            raise LiveOrderIdempotencyConflictError(
                "Idempotency key is already bound to different order content: "
                f"{key}"
            )

        return False

    def get(
        self,
        idempotency_key: str,
    ) -> LiveOrderIdempotencyReservation | None:
        key = self._required(idempotency_key, "idempotency_key")

        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"""
                    SELECT
                        idempotency_key,
                        order_fingerprint,
                        order_id,
                        signal_id,
                        reserved_at
                    FROM {self.TABLE_NAME}
                    WHERE idempotency_key = ?
                    """,
                    (key,),
                ).fetchone()
        except sqlite3.Error as error:
            raise LiveOrderIdempotencyRepositoryError(
                f"Could not read live-order idempotency key: {key}"
            ) from error

        if row is None:
            return None

        return LiveOrderIdempotencyReservation(
            idempotency_key=str(row[0]),
            order_fingerprint=str(row[1]),
            order_id=str(row[2]),
            signal_id=str(row[3]),
            reserved_at=datetime.fromisoformat(str(row[4])),
        )

    def count(self) -> int:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"SELECT COUNT(*) FROM {self.TABLE_NAME}"
                ).fetchone()
        except sqlite3.Error as error:
            raise LiveOrderIdempotencyRepositoryError(
                "Could not count live-order idempotency reservations."
            ) from error

        return 0 if row is None else int(row[0])

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with self._connect() as connection:
                connection.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        idempotency_key TEXT NOT NULL UNIQUE,
                        order_fingerprint TEXT NOT NULL,
                        order_id TEXT NOT NULL,
                        signal_id TEXT NOT NULL,
                        reserved_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS
                        idx_live_order_idempotency_order_id
                    ON {self.TABLE_NAME} (order_id)
                    """
                )
                connection.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS
                        idx_live_order_idempotency_signal_id
                    ON {self.TABLE_NAME} (signal_id)
                    """
                )
                connection.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS
                        idx_live_order_idempotency_reserved_at
                    ON {self.TABLE_NAME} (reserved_at DESC)
                    """
                )
                connection.commit()
        except sqlite3.Error as error:
            raise LiveOrderIdempotencyRepositoryError(
                "Could not initialize live-order idempotency storage."
            ) from error

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=30.0,
        )
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

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
