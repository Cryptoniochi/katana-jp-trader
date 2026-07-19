"""MarketSessionRunnerのテスト。"""

from datetime import datetime, timezone

from app.market.market_clock import (
    TokyoMarketClockSnapshot,
)
from app.market.market_session import (
    TokyoMarketSession,
)
from app.runtime.session_runner import (
    MarketSessionRunDecision,
    MarketSessionRunner,
)


NOW = datetime(
    2026,
    7,
    21,
    0,
    0,
    tzinfo=timezone.utc,
)


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


def snapshot(
    *,
    business_day=True,
    session=TokyoMarketSession.MORNING,
    wait_seconds=0.0,
) -> TokyoMarketClockSnapshot:
    return TokyoMarketClockSnapshot(
        observed_at=NOW,
        local_at=NOW,
        business_day=business_day,
        session=session,
        next_trading_at=NOW,
        wait_seconds=wait_seconds,
    )


def test_open_market_executes_application() -> None:
    calls = []
    runner = MarketSessionRunner(
        market_clock=SequenceClock(
            (snapshot(),)
        ),
        now_provider=lambda: NOW,
    )

    result = runner.run(
        lambda: calls.append("run") or 0
    )

    assert result.decision is (
        MarketSessionRunDecision.EXECUTED
    )
    assert result.application_exit_code == 0
    assert calls == ["run"]


def test_non_business_day_is_skipped() -> None:
    runner = MarketSessionRunner(
        market_clock=SequenceClock(
            (
                snapshot(
                    business_day=False,
                    session=TokyoMarketSession.CLOSED,
                    wait_seconds=3600,
                ),
            )
        ),
        now_provider=lambda: NOW,
    )

    result = runner.run(
        lambda: 99
    )

    assert result.decision is (
        MarketSessionRunDecision
        .SKIPPED_NON_BUSINESS_DAY
    )
    assert result.application_exit_code is None


def test_after_close_is_skipped() -> None:
    runner = MarketSessionRunner(
        market_clock=SequenceClock(
            (
                snapshot(
                    session=(
                        TokyoMarketSession.AFTER_CLOSE
                    ),
                ),
            )
        ),
        now_provider=lambda: NOW,
    )

    result = runner.run(
        lambda: 99
    )

    assert result.decision is (
        MarketSessionRunDecision
        .SKIPPED_AFTER_CLOSE
    )


def test_pre_open_waits_in_bounded_chunks() -> None:
    sleeps = []
    runner = MarketSessionRunner(
        market_clock=SequenceClock(
            (
                snapshot(
                    session=TokyoMarketSession.PRE_OPEN,
                    wait_seconds=120.0,
                ),
                snapshot(
                    session=TokyoMarketSession.MORNING,
                ),
            )
        ),
        now_provider=lambda: NOW,
        sleeper=sleeps.append,
        maximum_sleep_seconds=30.0,
    )

    result = runner.run(
        lambda: 0
    )

    assert result.decision is (
        MarketSessionRunDecision.EXECUTED
    )
    assert result.waited_seconds == 30.0
    assert sleeps == [30.0]


def test_stop_request_prevents_execution() -> None:
    runner = MarketSessionRunner(
        market_clock=SequenceClock(
            (snapshot(),)
        ),
        now_provider=lambda: NOW,
        stop_requested=lambda: True,
    )

    result = runner.run(
        lambda: 99
    )

    assert result.decision is (
        MarketSessionRunDecision.STOP_REQUESTED
    )
