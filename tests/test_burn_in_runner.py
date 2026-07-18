"""BurnInRunnerのテスト。"""

from datetime import datetime, timedelta, timezone

from app.application.trading_loop_models import (
    TradingLoopCycleStatus,
)
from app.runtime.burn_in_models import (
    BurnInSettings,
    BurnInStopReason,
)
from app.runtime.burn_in_runner import BurnInRunner


BASE = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


class Clock:
    def __init__(self) -> None:
        self.current = BASE

    def __call__(self) -> datetime:
        value = self.current
        self.current += timedelta(seconds=1)
        return value


class FakeCycle:
    def __init__(
        self,
        number: int,
        status: TradingLoopCycleStatus,
    ) -> None:
        self.cycle_number = number
        self.status = status
        self.error_message = (
            "failed"
            if status is TradingLoopCycleStatus.FAILED
            else None
        )

    @property
    def is_successful(self) -> bool:
        return (
            self.status
            is TradingLoopCycleStatus.COMPLETED
        )

    @property
    def signal_count(self) -> int:
        return 0

    @property
    def execution_count(self) -> int:
        return 0


class FakeComponent:
    def __init__(
        self,
        statuses,
        *,
        raises_at: int | None = None,
    ) -> None:
        self.statuses = list(statuses)
        self.raises_at = raises_at
        self.calls = 0

    def run_cycle(self):
        self.calls += 1

        if self.raises_at == self.calls:
            raise RuntimeError("burn-in error")

        return FakeCycle(
            self.calls,
            self.statuses[self.calls - 1],
        )


def test_runner_stops_at_maximum_cycles() -> None:
    clock = Clock()
    runner = BurnInRunner(
        component=FakeComponent(
            (
                TradingLoopCycleStatus.COMPLETED,
                TradingLoopCycleStatus.COMPLETED,
            )
        ),
        settings=BurnInSettings(
            maximum_cycles=2,
            cycle_interval_seconds=0.0,
        ),
        now_provider=clock,
        sleeper=lambda _seconds: None,
    )

    result = runner.run()

    assert result.stop_reason is (
        BurnInStopReason.MAX_CYCLES_REACHED
    )
    assert result.cycle_count == 2
    assert result.successful_cycle_count == 2


def test_runner_stops_at_consecutive_failure_limit() -> None:
    clock = Clock()
    runner = BurnInRunner(
        component=FakeComponent(
            (
                TradingLoopCycleStatus.FAILED,
                TradingLoopCycleStatus.FAILED,
            )
        ),
        settings=BurnInSettings(
            maximum_cycles=10,
            maximum_consecutive_failures=2,
        ),
        now_provider=clock,
        sleeper=lambda _seconds: None,
    )

    result = runner.run()

    assert result.stop_reason is (
        BurnInStopReason.CONSECUTIVE_FAILURE_LIMIT
    )
    assert result.failed_cycle_count == 2
    assert result.maximum_consecutive_failures == 2


def test_runner_stops_on_resource_critical() -> None:
    clock = Clock()
    runner = BurnInRunner(
        component=FakeComponent(
            (
                TradingLoopCycleStatus.RESOURCE_CRITICAL,
            )
        ),
        settings=BurnInSettings(
            maximum_cycles=10,
            stop_on_resource_critical=True,
        ),
        now_provider=clock,
        sleeper=lambda _seconds: None,
    )

    result = runner.run()

    assert result.stop_reason is (
        BurnInStopReason.RESOURCE_CRITICAL
    )
    assert result.cycle_count == 1


def test_runner_converts_exception_to_error_result() -> None:
    clock = Clock()
    runner = BurnInRunner(
        component=FakeComponent(
            (TradingLoopCycleStatus.COMPLETED,),
            raises_at=1,
        ),
        settings=BurnInSettings(maximum_cycles=5),
        now_provider=clock,
    )

    result = runner.run()

    assert result.stop_reason is BurnInStopReason.ERROR
    assert result.error_message == "burn-in error"
    assert result.cycle_count == 0
