"""Sprint 118 Runtime損益整合性のテスト。"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.runtime.paper_trading_runtime import (
    PaperTradingRuntime,
)
from app.trading.portfolio_models import PortfolioSnapshot

NOW = datetime(
    2026,
    8,
    6,
    6,
    30,
    tzinfo=timezone.utc,
)


def snapshot(
    *,
    equity: float,
    cash: float,
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        currency="JPY",
        cash_balance=cash,
        buying_power=cash,
        broker_market_value=0.0,
        broker_equity=equity,
        positions=(),
        generated_at=NOW,
    )


class FakePortfolioReader:
    def __init__(self) -> None:
        self.values = [
            snapshot(
                equity=10_000_000.0,
                cash=10_000_000.0,
            ),
            snapshot(
                equity=9_999_570.0,
                cash=9_999_570.0,
            ),
        ]

    def create_snapshot(self, *, generated_at=None):
        return self.values.pop(0)


class UnusedCycleRunner:
    def run_cycle(self):
        raise AssertionError("cycle must not run")


def test_reconciles_realized_pnl_and_external_executions(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "runtime.json"
    runtime = PaperTradingRuntime(
        cycle_runner=UnusedCycleRunner(),
        portfolio_reader=FakePortfolioReader(),
        status_path=status_path,
        now_provider=lambda: NOW,
    )

    runtime.start()
    runtime.record_external_executions(5)
    summary = runtime.complete()

    assert summary.execution_count == 5
    assert summary.net_profit_loss == -430.0

    payload = json.loads(
        status_path.read_text(encoding="utf-8")
    )
    assert payload["execution_count"] == 5
    assert payload["external_execution_count"] == 5
    assert payload["session_equity_change"] == -430.0
    assert payload["realized_profit_loss"] == -430.0
    assert payload["unrealized_profit_loss_change"] == 0.0
    assert payload["pnl_consistent"] is True


def test_execution_ledger_is_authoritative_at_completion(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE trade_signals (
                signal_id TEXT PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                action TEXT NOT NULL,
                generated_at TEXT NOT NULL
            );
            CREATE TABLE trade_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT NOT NULL UNIQUE,
                signal_id TEXT NOT NULL,
                code TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                execution_price REAL NOT NULL,
                executed_at TEXT NOT NULL,
                commission REAL NOT NULL DEFAULT 0,
                slippage REAL NOT NULL DEFAULT 0
            );
            INSERT INTO trade_signals VALUES
                ('buy-1', 'orb', 'buy', '2026-08-06T00:10:00+00:00'),
                ('exit-1', 'orb', 'exit', '2026-08-06T06:00:00+00:00');
            INSERT INTO trade_executions (
                execution_id, signal_id, code, side, quantity,
                execution_price, executed_at, commission, slippage
            ) VALUES
                ('e1', 'buy-1', '7203', 'buy', 100, 3000,
                 '2026-08-06T00:10:00+00:00', 0, 0),
                ('e2', 'exit-1', '7203', 'sell', 100, 3020,
                 '2026-08-06T06:00:00+00:00', 0, 0);
            """
        )

    status_path = tmp_path / "runtime.json"
    runtime = PaperTradingRuntime(
        cycle_runner=UnusedCycleRunner(),
        portfolio_reader=FakePortfolioReader(),
        database_path=database,
        status_path=status_path,
        now_provider=lambda: NOW,
    )

    runtime.start()
    summary = runtime.complete()
    payload = json.loads(status_path.read_text(encoding="utf-8"))

    assert summary.signal_count == 2
    assert summary.execution_count == 2
    assert summary.completed_trade_count == 1
    assert summary.net_profit_loss == 2000.0
    assert payload["net_profit_loss"] == 2000.0
    assert payload["realized_profit_loss"] == 2000.0
    assert payload["realized_profit_loss_source"] == "execution_ledger_fifo"
    assert payload["execution_ledger_balanced"] is True
    assert payload["pnl_consistent"] is False
