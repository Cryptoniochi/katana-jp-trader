"""Backtest Runtime JSON変換のテスト。"""

import json
from datetime import datetime, timezone

from app.backtest.backtest_runtime_models import (
    BacktestRuntimeResult,
    BacktestRuntimeStatus,
)
from app.backtest.backtest_runtime_report import (
    backtest_runtime_result_to_dict,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeEquityCurve:
    initial_equity = 1_000_000.0
    final_equity = 1_050_000.0
    absolute_profit_loss = 50_000.0
    total_return = 0.05
    maximum_drawdown = 0.02
    maximum_drawdown_amount = 20_000.0


class FakeRunResult:
    frame_count = 100
    signal_count = 5
    queued_count = 4
    execution_count = 4
    equity_curve_report = FakeEquityCurve()


class FakeMetrics:
    trade_count = 2
    winning_trade_count = 1
    losing_trade_count = 1
    flat_trade_count = 0
    gross_profit = 60_000.0
    gross_loss = 10_000.0
    net_profit_loss = 50_000.0
    win_rate = 0.5
    profit_factor = 6.0
    expectancy = 25_000.0
    maximum_consecutive_wins = 1
    maximum_consecutive_losses = 1


def test_completed_result_is_json_compatible() -> None:
    result = BacktestRuntimeResult(
        started_at=NOW,
        completed_at=NOW,
        status=BacktestRuntimeStatus.COMPLETED,
        run_result=FakeRunResult(),
        trade_report=object(),
        metrics=FakeMetrics(),
    )

    payload = backtest_runtime_result_to_dict(result)
    serialized = json.dumps(payload)

    assert payload["status"] == "completed"
    assert payload["frame_count"] == 100
    assert payload["metrics"]["profit_factor"] == 6.0
    assert payload["equity_curve"]["total_return"] == 0.05
    assert "completed" in serialized


def test_failed_result_has_null_analysis() -> None:
    result = BacktestRuntimeResult(
        started_at=NOW,
        completed_at=NOW,
        status=BacktestRuntimeStatus.FAILED,
        run_result=None,
        trade_report=None,
        metrics=None,
        error_message="failed",
    )

    payload = backtest_runtime_result_to_dict(result)

    assert payload["status"] == "failed"
    assert payload["metrics"] is None
    assert payload["equity_curve"] is None
