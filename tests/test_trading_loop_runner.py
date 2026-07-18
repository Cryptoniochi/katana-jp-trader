"""TradingLoopRunnerのテスト。"""

from datetime import datetime, timezone

from app.application.trading_loop_models import (
    TradingLoopCycleStatus,
)
from app.application.trading_loop_runner import (
    TradingLoopRunner,
)
from app.application.trading_loop_runner_models import (
    TradingLoopRunnerSettings,
    TradingLoopRunnerStopReason,
)


NOW = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


class FakeCycle:
    def __init__(
        self,
        *,
        cycle_number: int,
        status: TradingLoopCycleStatus,
    ) -> None:
        self.cycle_number = cycle_number
        self.started_at = NOW
        self.completed_at = NOW
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
            raise RuntimeError("cycle error")

        return FakeCycle(
            cycle_number=self.calls,
            status=self.statuses[self.calls - 1],
        )


def test_runner_stops_at_maximum_cycles() -> None:
    sleeps = []
    runner = TradingLoopRunner(
        component=FakeComponent(
            (
                TradingLoopCycleStatus.COMPLETED,
                TradingLoopCycleStatus.COMPLETED,
            )
        ),
        settings=TradingLoopRunnerSettings(
            cycle_interval_seconds=5.0,
            maximum_cycles=2,
        ),
        now_provider=lambda: NOW,
        sleeper=sleeps.append,
    )

    result = runner.run()

    assert result.stop_reason is (
        TradingLoopRunnerStopReason.MAX_CYCLES_REACHED
    )
    assert result.cycle_count == 2
    assert result.successful_cycle_count == 2
    assert sleeps == [5.0]


def test_runner_stops_on_resource_critical() -> None:
    runner = TradingLoopRunner(
        component=FakeComponent(
            (
                TradingLoopCycleStatus.RESOURCE_CRITICAL,
            )
        ),
        settings=TradingLoopRunnerSettings(
            maximum_cycles=10,
            stop_on_resource_critical=True,
        ),
        now_provider=lambda: NOW,
        sleeper=lambda _seconds: None,
    )

    result = runner.run()

    assert result.stop_reason is (
        TradingLoopRunnerStopReason.RESOURCE_CRITICAL
    )
    assert result.cycle_count == 1


def test_runner_can_stop_on_failed_cycle() -> None:
    runner = TradingLoopRunner(
        component=FakeComponent(
            (
                TradingLoopCycleStatus.FAILED,
            )
        ),
        settings=TradingLoopRunnerSettings(
            stop_on_cycle_failure=True,
        ),
        now_provider=lambda: NOW,
        sleeper=lambda _seconds: None,
    )

    result = runner.run()

    assert result.stop_reason is (
        TradingLoopRunnerStopReason.CYCLE_FAILED
    )
    assert result.failed_cycle_count == 1


def test_runner_converts_exception_to_error_result() -> None:
    runner = TradingLoopRunner(
        component=FakeComponent(
            (
                TradingLoopCycleStatus.COMPLETED,
            ),
            raises_at=1,
        ),
        now_provider=lambda: NOW,
    )

    result = runner.run()

    assert result.stop_reason is (
        TradingLoopRunnerStopReason.ERROR
    )
    assert result.error_message == "cycle error"
    assert result.cycle_count == 0


def test_runner_honors_stop_request_before_first_cycle() -> None:
    component = FakeComponent(
        (
            TradingLoopCycleStatus.COMPLETED,
        )
    )
    runner = TradingLoopRunner(
        component=component,
        now_provider=lambda: NOW,
        stop_requested=lambda: True,
    )

    result = runner.run()

    assert result.stop_reason is (
        TradingLoopRunnerStopReason.STOP_REQUESTED
    )
    assert component.calls == 0
