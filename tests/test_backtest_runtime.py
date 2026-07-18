"""BacktestRuntimeのテスト。"""

from datetime import datetime, timezone

import pytest

from app.backtest.backtest_runtime import (
    BacktestRuntime,
)
from app.backtest.backtest_runtime_models import (
    BacktestRuntimeStatus,
)
from app.trading.order_models import OrderType


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeRunResult:
    frame_count = 10
    signal_count = 1
    queued_count = 1
    execution_count = 1
    equity_curve_report = None


class FakeExecutor:
    def __init__(self, *, raises: bool = False) -> None:
        self.raises = raises
        self.calls = []

    def run(
        self,
        *,
        order_type=OrderType.MARKET,
        equity_curve_limit=10_000,
        continue_on_error=False,
    ):
        self.calls.append(
            (
                order_type,
                equity_curve_limit,
                continue_on_error,
            )
        )

        if self.raises:
            raise RuntimeError("backtest failed")

        return FakeRunResult()


class FakeAnalyzer:
    def __init__(self) -> None:
        self.calls = []

    def create(self, run_result):
        self.calls.append(run_result)
        return object(), object()


def test_runtime_executes_and_analyzes() -> None:
    executor = FakeExecutor()
    analyzer = FakeAnalyzer()
    runtime = BacktestRuntime(
        executor=executor,
        analyzer=analyzer,
        now_provider=lambda: NOW,
    )

    result = runtime.run(
        order_type=OrderType.LIMIT,
        equity_curve_limit=500,
    )

    assert result.status is BacktestRuntimeStatus.COMPLETED
    assert result.frame_count == 10
    assert executor.calls == [
        (OrderType.LIMIT, 500, False)
    ]
    assert analyzer.calls == [result.run_result]


def test_runtime_can_return_failed_result() -> None:
    runtime = BacktestRuntime(
        executor=FakeExecutor(raises=True),
        analyzer=FakeAnalyzer(),
        now_provider=lambda: NOW,
    )

    result = runtime.run(
        continue_on_error=True
    )

    assert result.status is BacktestRuntimeStatus.FAILED
    assert result.error_message == "backtest failed"
    assert result.frame_count == 0


def test_runtime_can_raise_original_error() -> None:
    runtime = BacktestRuntime(
        executor=FakeExecutor(raises=True),
        analyzer=FakeAnalyzer(),
        now_provider=lambda: NOW,
    )

    with pytest.raises(
        RuntimeError,
        match="backtest failed",
    ):
        runtime.run(
            continue_on_error=False
        )


def test_runtime_rejects_invalid_equity_curve_limit() -> None:
    runtime = BacktestRuntime(
        executor=FakeExecutor(),
        analyzer=FakeAnalyzer(),
        now_provider=lambda: NOW,
    )

    with pytest.raises(
        ValueError,
        match="取得件数",
    ):
        runtime.run(
            equity_curve_limit=0
        )
