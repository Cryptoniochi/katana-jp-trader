"""Sprint 118 Runtime損益整合性のテスト。"""

import json
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
