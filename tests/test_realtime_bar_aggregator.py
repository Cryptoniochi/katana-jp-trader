"""リアルタイムバー集計器のテスト。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.market.market_data_provider import MarketDataTick
from app.market.realtime_bar_aggregator import (
    RealtimeBarAggregator,
)


TOKYO = ZoneInfo("Asia/Tokyo")


def tick(
    minute: int,
    second: int,
    price: float,
    cumulative_volume: float,
):
    return MarketDataTick(
        code="7203",
        observed_at=datetime(
            2026,
            7,
            29,
            9,
            minute,
            second,
            tzinfo=TOKYO,
        ),
        price=price,
        cumulative_volume=cumulative_volume,
    )


def test_aggregates_ohlcv_and_completes_on_next_bucket() -> None:
    completed = []
    aggregator = RealtimeBarAggregator(
        interval_minutes=5,
        on_completed_bar=completed.append,
    )

    assert aggregator.ingest(
        tick(0, 1, 100, 1000)
    ) is None
    assert aggregator.ingest(
        tick(1, 0, 105, 1010)
    ) is None
    assert aggregator.ingest(
        tick(3, 0, 98, 1025)
    ) is None

    bar = aggregator.ingest(
        tick(5, 0, 110, 1030)
    )

    assert bar is not None
    assert bar.open_price == 100
    assert bar.high_price == 105
    assert bar.low_price == 98
    assert bar.close_price == 98
    assert bar.volume == 25
    assert completed == [bar]


def test_ignores_duplicate_or_old_tick() -> None:
    aggregator = RealtimeBarAggregator()

    first = tick(0, 1, 100, 1000)
    aggregator.ingest(first)

    assert aggregator.ingest(first) is None
