"""PaperTradingRuntimeのテスト。"""

from datetime import datetime, timezone

import pytest

from app.application.trading_loop_models import (
    TradingLoopCycleStatus,
)
from app.runtime.paper_trading_runtime import (
    PaperTradingRuntime,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingRuntimeStatus,
)
from app.trading.portfolio_models import PortfolioSnapshot


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeCycle:
    def __init__(self, number: int) -> None:
        self.cycle_number = number
        self.status = TradingLoopCycleStatus.COMPLETED
        self.error_message = None

    @property
    def is_successful(self) -> bool:
        return True

    @property
    def signal_count(self) -> int:
        return 1

    @property
    def execution_count(self) -> int:
        return 1


class FakeCycleRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run_cycle(self):
        self.calls += 1
        return FakeCycle(self.calls)


class FakePortfolioReader:
    def __init__(self, equities) -> None:
        self.equities = list(equities)
        self.calls = 0

    def create_snapshot(
        self,
        *,
        generated_at=None,
    ) -> PortfolioSnapshot:
        equity = self.equities[self.calls]
        self.calls += 1
        return PortfolioSnapshot(
            currency="JPY",
            cash_balance=equity,
            buying_power=equity,
            broker_market_value=0.0,
            broker_equity=equity,
            positions=(),
            generated_at=generated_at,
        )


def create_runtime():
    return PaperTradingRuntime(
        cycle_runner=FakeCycleRunner(),
        portfolio_reader=FakePortfolioReader(
            (
                1_000_000.0,
                1_005_000.0,
                1_010_000.0,
                1_010_000.0,
            )
        ),
        now_provider=lambda: NOW,
    )


def test_runtime_records_cycles_and_completes() -> None:
    runtime = create_runtime()

    runtime.start()
    runtime.run_cycle()
    runtime.run_cycle()
    summary = runtime.complete()

    assert summary.status is (
        PaperTradingRuntimeStatus.COMPLETED
    )
    assert summary.cycle_count == 2
    assert summary.initial_equity == 1_000_000.0
    assert summary.final_equity == 1_010_000.0
    assert summary.net_profit_loss == 10_000.0
    assert len(runtime.records()) == 2


def test_runtime_can_fail_with_summary() -> None:
    runtime = create_runtime()

    runtime.start()
    summary = runtime.fail(
        error_message="runtime failed"
    )

    assert summary.status is (
        PaperTradingRuntimeStatus.FAILED
    )
    assert summary.error_message == "runtime failed"


def test_runtime_rejects_cycle_before_start() -> None:
    runtime = create_runtime()

    with pytest.raises(
        RuntimeError,
        match="稼働していません",
    ):
        runtime.run_cycle()


def test_runtime_rejects_double_start() -> None:
    runtime = create_runtime()
    runtime.start()

    with pytest.raises(
        RuntimeError,
        match="すでに稼働中",
    ):
        runtime.start()
