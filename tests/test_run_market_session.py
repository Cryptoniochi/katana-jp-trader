"""市場セッション運用CLIのテスト。"""

from datetime import datetime, timezone
from io import StringIO

from app.market.market_clock import (
    TokyoMarketClockSnapshot,
)
from app.market.market_session import (
    TokyoMarketSession,
)
from app.run_market_session import run


NOW = datetime(
    2026,
    7,
    21,
    0,
    0,
    tzinfo=timezone.utc,
)


class StaticClock:
    def __init__(self, snapshot) -> None:
        self.value = snapshot

    def snapshot(self, _observed_at):
        return self.value


def market_snapshot(
    *,
    business_day=True,
    session=TokyoMarketSession.MORNING,
) -> TokyoMarketClockSnapshot:
    return TokyoMarketClockSnapshot(
        observed_at=NOW,
        local_at=NOW,
        business_day=business_day,
        session=session,
        next_trading_at=NOW,
        wait_seconds=0.0,
    )


def no_gateway(_environ):
    return None


def test_open_market_forwards_arguments() -> None:
    captured = {}

    def paper_runner(
        argv,
        *,
        environ,
        output,
        error_output,
    ):
        captured["argv"] = argv
        captured["environ"] = environ
        return 7

    exit_code = run(
        [
            "--maximum-sleep-seconds",
            "5",
            "--maximum-cycles",
            "1",
        ],
        environ={"TEST": "1"},
        output=StringIO(),
        error_output=StringIO(),
        now_provider=lambda: NOW,
        market_clock=StaticClock(
            market_snapshot()
        ),
        paper_trading_runner=paper_runner,
        notification_gateway_factory=no_gateway,
    )

    assert exit_code == 7
    assert captured["argv"] == [
        "--maximum-cycles",
        "1",
    ]
    assert captured["environ"] == {
        "TEST": "1",
    }


def test_non_business_day_does_not_run_paper_trading() -> None:
    calls = []

    exit_code = run(
        [],
        output=StringIO(),
        error_output=StringIO(),
        now_provider=lambda: NOW,
        market_clock=StaticClock(
            market_snapshot(
                business_day=False,
                session=TokyoMarketSession.CLOSED,
            )
        ),
        paper_trading_runner=(
            lambda *args, **kwargs: calls.append(1)
        ),
        notification_gateway_factory=no_gateway,
    )

    assert exit_code == 0
    assert calls == []


def test_after_close_does_not_run_paper_trading() -> None:
    calls = []

    exit_code = run(
        [],
        output=StringIO(),
        error_output=StringIO(),
        now_provider=lambda: NOW,
        market_clock=StaticClock(
            market_snapshot(
                session=TokyoMarketSession.AFTER_CLOSE,
            )
        ),
        paper_trading_runner=(
            lambda *args, **kwargs: calls.append(1)
        ),
        notification_gateway_factory=no_gateway,
    )

    assert exit_code == 0
    assert calls == []
