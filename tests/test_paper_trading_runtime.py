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


class FakeRiskResult:
    def __init__(
        self,
        *,
        allows_new_entries: bool,
        approved_quantity: int,
    ) -> None:
        self.allows_new_entries = allows_new_entries
        self.is_blocked = not allows_new_entries
        self.approved_quantity = (
            approved_quantity
            if allows_new_entries
            else 0
        )


class FakeRiskRunRecord:
    def __init__(self, result) -> None:
        self.result = result


class FakeRiskRunner:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = []

    def run(
        self,
        *,
        cycle_result,
        portfolio_snapshot,
        evaluated_at,
    ):
        self.calls.append(
            {
                "cycle_result": cycle_result,
                "portfolio_snapshot": portfolio_snapshot,
                "evaluated_at": evaluated_at,
            }
        )

        return FakeRiskRunRecord(
            self.results[len(self.calls) - 1]
        )


def create_runtime(
    *,
    risk_runner=None,
):
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
        risk_runner=risk_runner,
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
    assert summary.risk_evaluated_cycle_count == 0
    assert summary.risk_blocked_cycle_count == 0
    assert summary.latest_risk_result is None


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


def test_runtime_runs_risk_after_portfolio_snapshot() -> None:
    risk_result = FakeRiskResult(
        allows_new_entries=True,
        approved_quantity=200,
    )
    risk_runner = FakeRiskRunner((risk_result,))
    runtime = create_runtime(
        risk_runner=risk_runner,
    )

    runtime.start()
    record = runtime.run_cycle()

    assert len(risk_runner.calls) == 1
    call = risk_runner.calls[0]
    assert call["cycle_result"] is record.cycle_result
    assert (
        call["portfolio_snapshot"]
        is record.portfolio_snapshot
    )
    assert call["evaluated_at"] == NOW
    assert record.risk_result is risk_result
    assert record.has_risk_result
    assert record.allows_new_entries is True
    assert runtime.last_risk_result is risk_result


def test_runtime_records_blocked_risk_result() -> None:
    risk_result = FakeRiskResult(
        allows_new_entries=False,
        approved_quantity=200,
    )
    runtime = create_runtime(
        risk_runner=FakeRiskRunner((risk_result,)),
    )

    runtime.start()
    record = runtime.run_cycle()
    summary = runtime.complete()

    assert record.allows_new_entries is False
    assert summary.risk_evaluated_cycle_count == 1
    assert summary.risk_blocked_cycle_count == 1
    assert summary.latest_risk_result is risk_result


def test_runtime_tracks_latest_risk_result() -> None:
    first_result = FakeRiskResult(
        allows_new_entries=True,
        approved_quantity=100,
    )
    second_result = FakeRiskResult(
        allows_new_entries=False,
        approved_quantity=100,
    )
    runtime = create_runtime(
        risk_runner=FakeRiskRunner(
            (
                first_result,
                second_result,
            )
        ),
    )

    runtime.start()
    runtime.run_cycle()
    runtime.run_cycle()

    assert runtime.last_risk_result is second_result
    assert runtime.records()[0].risk_result is first_result
    assert runtime.records()[1].risk_result is second_result


def test_runtime_without_risk_runner_is_backward_compatible() -> None:
    runtime = create_runtime()

    runtime.start()
    record = runtime.run_cycle()

    assert record.risk_result is None
    assert not record.has_risk_result
    assert record.allows_new_entries is None
    assert runtime.last_risk_result is None
