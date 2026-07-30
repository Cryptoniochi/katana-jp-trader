"""kabuステーション完成Bar Providerのテスト。"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.market.kabu_station_completed_bar_provider import (
    KabuStationCompletedBarProvider,
)
from app.market.realtime_bar_aggregator import RealtimeBar


JST = ZoneInfo("Asia/Tokyo")


def make_bar(
    *,
    code: str = "7203",
    minute: int = 0,
    close_price: float = 1005.0,
) -> RealtimeBar:
    return RealtimeBar(
        code=code,
        started_at=datetime(
            2026, 7, 30, 9, minute, tzinfo=JST
        ),
        ended_at=datetime(
            2026, 7, 30, 9, minute + 5, tzinfo=JST
        ),
        open_price=1000.0,
        high_price=1010.0,
        low_price=995.0,
        close_price=close_price,
        volume=1234.0,
    )


def test_accepts_and_returns_stock_prices() -> None:
    provider = KabuStationCompletedBarProvider()
    provider.accept(make_bar())

    bars = provider("7203", date(2026, 7, 30))

    assert len(bars) == 1
    assert bars[0].code == "7203"
    assert bars[0].close == 1005.0
    assert bars[0].volume == 1234


def test_replaces_same_code_and_datetime() -> None:
    provider = KabuStationCompletedBarProvider()
    provider.accept(make_bar(close_price=1005.0))
    provider.accept(make_bar(close_price=1008.0))

    bars = provider("7203", date(2026, 7, 30))

    assert len(bars) == 1
    assert bars[0].close == 1008.0
    assert provider.count() == 1
