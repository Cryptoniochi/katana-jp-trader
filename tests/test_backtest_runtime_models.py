"""Backtest Runtimeモデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.backtest.backtest_runtime_models import (
    BacktestRuntimeResult,
    BacktestRuntimeStatus,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeRunResult:
    frame_count = 100
    signal_count = 3
    queued_count = 2
    execution_count = 2
    equity_curve_report = None


def test_completed_result_exposes_counts() -> None:
    result = BacktestRuntimeResult(
        started_at=NOW,
        completed_at=NOW,
        status=BacktestRuntimeStatus.COMPLETED,
        run_result=FakeRunResult(),
        trade_report=object(),
        metrics=object(),
    )

    assert result.is_successful
    assert result.frame_count == 100
    assert result.signal_count == 3
    assert result.order_count == 2
    assert result.execution_count == 2
    assert result.elapsed_seconds == 0.0


def test_completed_result_requires_analysis_outputs() -> None:
    with pytest.raises(
        ValueError,
        match="取引レポート",
    ):
        BacktestRuntimeResult(
            started_at=NOW,
            completed_at=NOW,
            status=BacktestRuntimeStatus.COMPLETED,
            run_result=FakeRunResult(),
            trade_report=None,
            metrics=None,
        )


def test_failed_result_requires_error_message() -> None:
    with pytest.raises(
        ValueError,
        match="エラーメッセージ",
    ):
        BacktestRuntimeResult(
            started_at=NOW,
            completed_at=NOW,
            status=BacktestRuntimeStatus.FAILED,
            run_result=None,
            trade_report=None,
            metrics=None,
        )
