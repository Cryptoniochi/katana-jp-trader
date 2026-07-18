"""TokyoMarketClockのテスト。"""

from datetime import datetime, timezone

from app.market.market_clock import (
    TokyoMarketClock,
)
from app.market.market_session import (
    TokyoMarketSession,
)


def utc(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
) -> datetime:
    return datetime(
        year,
        month,
        day,
        hour,
        minute,
        tzinfo=timezone.utc,
    )


def test_morning_session_is_open() -> None:
    clock = TokyoMarketClock()

    snapshot = clock.snapshot(
        utc(2026, 7, 21, 0, 30)
    )

    assert snapshot.business_day
    assert snapshot.session is TokyoMarketSession.MORNING
    assert snapshot.is_open
    assert snapshot.wait_seconds == 0.0


def test_lunch_waits_until_afternoon_open() -> None:
    clock = TokyoMarketClock()

    snapshot = clock.snapshot(
        utc(2026, 7, 21, 3, 0)
    )

    assert snapshot.session is TokyoMarketSession.LUNCH
    assert not snapshot.is_open
    assert snapshot.next_trading_at.hour == 12
    assert snapshot.next_trading_at.minute == 30
    assert snapshot.wait_seconds == 1800.0


def test_after_close_waits_until_next_business_day() -> None:
    clock = TokyoMarketClock()

    snapshot = clock.snapshot(
        utc(2026, 7, 21, 7, 0)
    )

    assert snapshot.session is TokyoMarketSession.AFTER_CLOSE
    assert snapshot.next_trading_at.date().isoformat() == "2026-07-22"
    assert snapshot.next_trading_at.hour == 9


def test_market_holiday_waits_until_next_business_day() -> None:
    clock = TokyoMarketClock()

    snapshot = clock.snapshot(
        utc(2026, 7, 20, 0, 0)
    )

    assert not snapshot.business_day
    assert snapshot.session is TokyoMarketSession.CLOSED
    assert snapshot.next_trading_at.date().isoformat() == "2026-07-21"
