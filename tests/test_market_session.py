"""TokyoMarketSessionScheduleのテスト。"""

from datetime import time

from app.market.market_session import (
    TokyoMarketSession,
    TokyoMarketSessionSchedule,
)


def test_session_boundaries() -> None:
    schedule = TokyoMarketSessionSchedule()

    assert schedule.resolve(
        time(7, 59)
    ) is TokyoMarketSession.CLOSED
    assert schedule.resolve(
        time(8, 0)
    ) is TokyoMarketSession.PRE_OPEN
    assert schedule.resolve(
        time(9, 0)
    ) is TokyoMarketSession.MORNING
    assert schedule.resolve(
        time(11, 30)
    ) is TokyoMarketSession.MORNING
    assert schedule.resolve(
        time(11, 31)
    ) is TokyoMarketSession.LUNCH
    assert schedule.resolve(
        time(12, 30)
    ) is TokyoMarketSession.AFTERNOON
    assert schedule.resolve(
        time(15, 30)
    ) is TokyoMarketSession.AFTERNOON
    assert schedule.resolve(
        time(15, 31)
    ) is TokyoMarketSession.AFTER_CLOSE


def test_only_morning_and_afternoon_are_trading_sessions() -> None:
    assert TokyoMarketSessionSchedule.is_trading_session(
        TokyoMarketSession.MORNING
    )
    assert TokyoMarketSessionSchedule.is_trading_session(
        TokyoMarketSession.AFTERNOON
    )
    assert not TokyoMarketSessionSchedule.is_trading_session(
        TokyoMarketSession.LUNCH
    )
