"""kabuステーションTick Monitorのテスト。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.market.kabu_station_tick_monitor import (
    KabuStationTickMonitor,
)
from app.market.market_data_provider import MarketDataTick


JST = ZoneInfo("Asia/Tokyo")


def test_monitor_counts_ticks_and_codes() -> None:
    monitor = KabuStationTickMonitor(
        print_ticks=False
    )

    monitor(
        MarketDataTick(
            code="7203",
            observed_at=datetime(
                2026,
                7,
                29,
                9,
                0,
                tzinfo=JST,
            ),
            price=2500,
            cumulative_volume=1000,
        )
    )
    monitor(
        MarketDataTick(
            code="9984",
            observed_at=datetime(
                2026,
                7,
                29,
                9,
                1,
                tzinfo=JST,
            ),
            price=10000,
            cumulative_volume=2000,
        )
    )

    status = monitor.status()
    assert status.received_tick_count == 2
    assert status.received_codes == (
        "7203",
        "9984",
    )
    assert status.last_tick is not None
    assert status.last_tick.code == "9984"
