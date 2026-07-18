"""MarketAwareTradingLoopRunnerのテスト。"""

from datetime import datetime, timezone

from app.application.market_aware_trading_loop_runner import (
    MarketAwareTradingLoopRunner,
)
from app.application.trading_loop_models import (
    TradingLoopCycleStatus,
)
from app.application.trading_loop_runner_models import (
    TradingLoopRunnerStopReason,
)
from app.market.market_clock import (
    TokyoMarketClockSnapshot,
)
from app.market.market_session import (
    TokyoMarketSession,
)


NOW = datetime(
    2026,
    7,
    21,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeCycle:
    def __init__(self, number: int) -> None:
        self.cycle_number = number
        self.started_at = NOW
        self.completed_at = NOW
        self.status = TradingLoopCycleStatus.COMPLETED
        self.error_message = None

    @property
    def is_successful(self) -> bool:
        return True

    @property
    def signal_count(self) -> int:
        return 0

    @property
    def execution_count(self) -> int:
        return 0


class FakeComponent:
    def __init__(self) -> None:
        self.calls = 0

    def run_cycle(self):
        self.calls += 1
        return FakeCycle(self.calls)


class SequenceClock:
    def __init__(self, snapshots) -> None:
        self.snapshots = list(snapshots)
        self.calls = 0

    def snapshot(self, _observed_at):
        index = min(
            self.calls,
            len(self.snapshots) - 1,
        )
        self.calls += 1
        return self.snapshots[index]


def clock_snapshot(
    *,
    session: TokyoMarketSession,
    wait_seconds: float,
) -> TokyoMarketClockSnapshot:
    return TokyoMarketClockSnapshot(
        observed_at=NOW,
        local_at=NOW,
        business_day=(
            session is not TokyoMarketSession.CLOSED
        ),
        session=session,
        next_trading_at=NOW,
        wait_seconds=wait_seconds,
    )


def test_runner_waits_while_market_closed_then_runs() -> None:
    component = FakeComponent()
    sleeps = []
    market_clock = SequenceClock(
        (
            clock_snapshot(
                session=TokyoMarketSession.LUNCH,
                wait_seconds=1800.0,
            ),
            clock_snapshot(
                session=TokyoMarketSession.MORNING,
                wait_seconds=0.0,
            ),
        )
    )
    runner = MarketAwareTradingLoopRunner(
        component=component,
        market_clock=market_clock,
        cycle_interval_seconds=10.0,
        maximum_cycles=1,
        now_provider=lambda: NOW,
        sleeper=sleeps.append,
    )

    result = runner.run()

    assert result.stop_reason is (
        TradingLoopRunnerStopReason.MAX_CYCLES_REACHED
    )
    assert component.calls == 1
    assert sleeps == [300.0]


def test_runner_can_stop_immediately_after_close() -> None:
    component = FakeComponent()
    runner = MarketAwareTradingLoopRunner(
        component=component,
        market_clock=SequenceClock(
            (
                clock_snapshot(
                    session=TokyoMarketSession.AFTER_CLOSE,
                    wait_seconds=60000.0,
                ),
            )
        ),
        stop_after_market_close=True,
        now_provider=lambda: NOW,
        sleeper=lambda _seconds: None,
    )

    result = runner.run()

    assert result.stop_reason is (
        TradingLoopRunnerStopReason.STOP_REQUESTED
    )
    assert component.calls == 0


def test_runner_honors_external_stop_request() -> None:
    component = FakeComponent()
    runner = MarketAwareTradingLoopRunner(
        component=component,
        market_clock=SequenceClock(
            (
                clock_snapshot(
                    session=TokyoMarketSession.MORNING,
                    wait_seconds=0.0,
                ),
            )
        ),
        now_provider=lambda: NOW,
        stop_requested=lambda: True,
    )

    result = runner.run()

    assert result.stop_reason is (
        TradingLoopRunnerStopReason.STOP_REQUESTED
    )
    assert component.calls == 0
