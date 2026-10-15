"""Durable registry of Live BUY executions that still require reconciliation."""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from app.live.live_production_runner import LiveEntryIntent
from app.trading.order_models import OrderSide, OrderType, TradeOrder


class LiveEntryReconciliationState(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class LivePendingEntryExecution:
    execution_key: str
    trading_date: date
    order_id: str
    signal_id: str
    code: str
    quantity: int
    state: LiveEntryReconciliationState

    def to_order(self) -> TradeOrder:
        return TradeOrder(
            order_id=self.order_id,
            signal_id=self.signal_id,
            code=self.code,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=self.quantity,
        )


class LiveDailyEntryLimitError(RuntimeError):
    """Raised before transport when the durable daily Live-entry cap is reached."""


class SQLiteLiveEntryReconciliationRegistry:
    """Crash-safe queue prepared before an entry can reach Live submission."""

    def __init__(self, database_path: Path, *, max_entries_per_day: int = 20) -> None:
        if isinstance(max_entries_per_day, bool) or max_entries_per_day <= 0:
            raise ValueError("max_entries_per_day must be a positive integer")
        self.database_path=Path(database_path)
        self.max_entries_per_day=int(max_entries_per_day)
        self.database_path.parent.mkdir(parents=True,exist_ok=True)
        with self._connect() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS live_entry_reconciliation_registry(
                execution_key TEXT PRIMARY KEY,
                trading_date TEXT NOT NULL,
                order_id TEXT NOT NULL,
                signal_id TEXT NOT NULL,
                code TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                state TEXT NOT NULL
            )""")

    def prepare(self, *, execution_key: str, trading_date: date, order: TradeOrder) -> LivePendingEntryExecution:
        key=str(execution_key or "").strip()
        if not key: raise ValueError("execution_key is required")
        if order.side is not OrderSide.BUY or order.order_type is not OrderType.MARKET:
            raise ValueError("Live entry reconciliation registry accepts BUY MARKET only.")
        candidate=(trading_date.isoformat(),order.order_id,order.signal_id,order.code,int(order.quantity))
        with self._connect() as c:
            # BEGIN IMMEDIATE makes the "count then reserve" operation atomic
            # even if two Live workers are accidentally started.
            c.execute("BEGIN IMMEDIATE")
            existing=c.execute("""SELECT trading_date,order_id,signal_id,code,quantity,state
                FROM live_entry_reconciliation_registry WHERE execution_key=?""",(key,)).fetchone()
            if existing is None:
                count=int(c.execute("""SELECT COUNT(*) FROM live_entry_reconciliation_registry
                    WHERE trading_date=?""",(trading_date.isoformat(),)).fetchone()[0])
                if count >= self.max_entries_per_day:
                    raise LiveDailyEntryLimitError(
                        f"Daily Live entry limit reached: {count}/{self.max_entries_per_day} "
                        f"for {trading_date.isoformat()}."
                    )
                c.execute("""INSERT INTO live_entry_reconciliation_registry
                    (execution_key,trading_date,order_id,signal_id,code,quantity,state)
                    VALUES(?,?,?,?,?,?,?)""",(key,*candidate,LiveEntryReconciliationState.PENDING.value))
            row=c.execute("""SELECT trading_date,order_id,signal_id,code,quantity,state
                FROM live_entry_reconciliation_registry WHERE execution_key=?""",(key,)).fetchone()
        if row is None: raise RuntimeError("Live entry reconciliation row disappeared.")
        existing=tuple(row[:5])
        if existing != candidate:
            raise RuntimeError("execution_key is already bound to a different Live entry.")
        return self.get_required(key)

    def count_for_date(self, trading_date: date) -> int:
        """Return durable entry reservations for one trading date."""
        with self._connect() as c:
            row=c.execute("""SELECT COUNT(*) FROM live_entry_reconciliation_registry
                WHERE trading_date=?""",(trading_date.isoformat(),)).fetchone()
        return int(row[0])

    def list_pending(self) -> tuple[LivePendingEntryExecution,...]:
        with self._connect() as c:
            rows=c.execute("""SELECT execution_key,trading_date,order_id,signal_id,code,quantity,state
                FROM live_entry_reconciliation_registry WHERE state=? ORDER BY rowid""",
                (LiveEntryReconciliationState.PENDING.value,)).fetchall()
        return tuple(self._record(r) for r in rows)

    def complete(self, execution_key: str) -> LivePendingEntryExecution:
        with self._connect() as c:
            c.execute("""UPDATE live_entry_reconciliation_registry SET state=?
                WHERE execution_key=? AND state=?""",
                (LiveEntryReconciliationState.COMPLETE.value,execution_key,
                 LiveEntryReconciliationState.PENDING.value))
        return self.get_required(execution_key)

    def get_required(self, execution_key: str) -> LivePendingEntryExecution:
        with self._connect() as c:
            row=c.execute("""SELECT execution_key,trading_date,order_id,signal_id,code,quantity,state
                FROM live_entry_reconciliation_registry WHERE execution_key=?""",
                (execution_key,)).fetchone()
        if row is None: raise KeyError(execution_key)
        return self._record(row)

    def _connect(self):
        c=sqlite3.connect(self.database_path,timeout=30.0)
        c.execute("PRAGMA busy_timeout=30000")
        return c

    @staticmethod
    def _record(row) -> LivePendingEntryExecution:
        return LivePendingEntryExecution(
            execution_key=str(row[0]),trading_date=date.fromisoformat(str(row[1])),
            order_id=str(row[2]),signal_id=str(row[3]),code=str(row[4]),quantity=int(row[5]),
            state=LiveEntryReconciliationState(str(row[6])))
