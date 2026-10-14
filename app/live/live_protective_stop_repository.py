"""Durable per-position protective-stop state for Live trading.

Stops are created only from confirmed Live fills.  No PaperBroker state is read
or imported here.  Rows remain durable across process restarts and are retired
when the authoritative Live account confirms that the position is gone.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Callable

NowProvider = Callable[[], datetime]


class LiveProtectiveStopState(StrEnum):
    ACTIVE = "active"
    EXIT_PENDING = "exit_pending"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class LiveProtectiveStopRecord:
    code: str
    entry_execution_key: str
    trading_date: date
    quantity: int
    fill_price: float
    stop_price: float
    stop_loss_rate: float
    state: LiveProtectiveStopState
    created_at: datetime
    updated_at: datetime

    @property
    def is_active(self) -> bool:
        return self.state is LiveProtectiveStopState.ACTIVE


class SQLiteLiveProtectiveStopRepository:
    """SQLite-backed stop state keyed by the Live entry execution key."""

    def __init__(
        self,
        database_path: Path,
        *,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._initialize()

    def record_filled_entry(
        self,
        *,
        code: str,
        entry_execution_key: str,
        trading_date: date,
        quantity: int,
        fill_price: float,
        stop_loss_rate: float = 0.01,
    ) -> LiveProtectiveStopRecord:
        normalized = self._code(code)
        key = entry_execution_key.strip()
        if not key:
            raise ValueError("entry_execution_key must not be empty")
        if isinstance(quantity, bool) or quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        if fill_price <= 0:
            raise ValueError("fill_price must be greater than zero")
        if not 0 < stop_loss_rate < 1:
            raise ValueError("stop_loss_rate must be between zero and one")
        now = self._now()
        stop_price = float(fill_price) * (1.0 - float(stop_loss_rate))

        existing = self.get_by_execution_key(key)
        if existing is not None:
            expected = (
                normalized,
                trading_date,
                int(quantity),
                float(fill_price),
                float(stop_loss_rate),
            )
            actual = (
                existing.code,
                existing.trading_date,
                existing.quantity,
                existing.fill_price,
                existing.stop_loss_rate,
            )
            if actual != expected:
                raise RuntimeError(
                    "Protective stop execution key already exists with "
                    "different confirmed-fill data."
                )
            return existing

        # Never attach a second active stop to the same symbol.  A previous
        # position must be authoritatively retired first.
        current = self.get_current(normalized)
        if current is not None:
            raise RuntimeError(
                f"Protective stop already exists for live symbol {normalized}."
            )

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO live_protective_stops (
                    code, entry_execution_key, trading_date, quantity,
                    fill_price, stop_price, stop_loss_rate, state,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized,
                    key,
                    trading_date.isoformat(),
                    int(quantity),
                    float(fill_price),
                    stop_price,
                    float(stop_loss_rate),
                    LiveProtectiveStopState.ACTIVE.value,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        return self.get_by_execution_key(key, required=True)

    def get_current(self, code: str) -> LiveProtectiveStopRecord | None:
        normalized = self._code(code)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM live_protective_stops
                WHERE code = ? AND state IN (?, ?)
                ORDER BY created_at DESC LIMIT 1
                """,
                (
                    normalized,
                    LiveProtectiveStopState.ACTIVE.value,
                    LiveProtectiveStopState.EXIT_PENDING.value,
                ),
            ).fetchone()
        return self._record(row)

    def list_current(self) -> tuple[LiveProtectiveStopRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM live_protective_stops
                WHERE state IN (?, ?)
                ORDER BY code, created_at
                """,
                (
                    LiveProtectiveStopState.ACTIVE.value,
                    LiveProtectiveStopState.EXIT_PENDING.value,
                ),
            ).fetchall()
        return tuple(self._record(row) for row in rows if row is not None)

    def get_by_execution_key(
        self, entry_execution_key: str, *, required: bool = False
    ) -> LiveProtectiveStopRecord | None:
        key = entry_execution_key.strip()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM live_protective_stops WHERE entry_execution_key = ?",
                (key,),
            ).fetchone()
        record = self._record(row)
        if required and record is None:
            raise KeyError(key)
        return record

    def mark_exit_pending(self, *, entry_execution_key: str) -> LiveProtectiveStopRecord:
        return self._transition(
            entry_execution_key=entry_execution_key,
            from_states=(LiveProtectiveStopState.ACTIVE,),
            to_state=LiveProtectiveStopState.EXIT_PENDING,
        )

    def retire(self, *, entry_execution_key: str) -> LiveProtectiveStopRecord:
        return self._transition(
            entry_execution_key=entry_execution_key,
            from_states=(
                LiveProtectiveStopState.ACTIVE,
                LiveProtectiveStopState.EXIT_PENDING,
            ),
            to_state=LiveProtectiveStopState.RETIRED,
        )

    def _transition(
        self,
        *,
        entry_execution_key: str,
        from_states: tuple[LiveProtectiveStopState, ...],
        to_state: LiveProtectiveStopState,
    ) -> LiveProtectiveStopRecord:
        current = self.get_by_execution_key(entry_execution_key, required=True)
        assert current is not None
        if current.state is to_state:
            return current
        if current.state not in from_states:
            raise RuntimeError(
                f"Invalid protective stop transition {current.state.value} "
                f"-> {to_state.value}."
            )
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE live_protective_stops
                SET state = ?, updated_at = ?
                WHERE entry_execution_key = ? AND state = ?
                """,
                (
                    to_state.value,
                    now.isoformat(),
                    entry_execution_key,
                    current.state.value,
                ),
            )
        return self.get_by_execution_key(entry_execution_key, required=True)

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS live_protective_stops (
                    code TEXT NOT NULL,
                    entry_execution_key TEXT PRIMARY KEY,
                    trading_date TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    fill_price REAL NOT NULL,
                    stop_price REAL NOT NULL,
                    stop_loss_rate REAL NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_live_protective_stops_code_state
                ON live_protective_stops(code, state)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _now(self) -> datetime:
        now = self.now_provider()
        if now.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime")
        return now

    @staticmethod
    def _code(value: str) -> str:
        code = str(value).strip()
        if not code:
            raise ValueError("code must not be empty")
        return code

    @staticmethod
    def _record(row: sqlite3.Row | None) -> LiveProtectiveStopRecord | None:
        if row is None:
            return None
        return LiveProtectiveStopRecord(
            code=str(row["code"]),
            entry_execution_key=str(row["entry_execution_key"]),
            trading_date=date.fromisoformat(str(row["trading_date"])),
            quantity=int(row["quantity"]),
            fill_price=float(row["fill_price"]),
            stop_price=float(row["stop_price"]),
            stop_loss_rate=float(row["stop_loss_rate"]),
            state=LiveProtectiveStopState(str(row["state"])),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )
