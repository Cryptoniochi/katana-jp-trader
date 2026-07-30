"""kabuステーションBar Sinkのテスト。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.market.kabu_station_bar_sink import (
    KabuStationBarRepositorySink,
)
from app.market.realtime_bar_aggregator import RealtimeBar


JST = ZoneInfo("Asia/Tokyo")


class FakeRepository:
    def __init__(self) -> None:
        self.calls = []

    def save_all(
        self,
        prices,
        interval_minutes,
        data_source,
    ):
        self.calls.append(
            (
                prices,
                interval_minutes,
                data_source,
            )
        )
        return len(prices)


def test_sink_converts_and_saves_realtime_bar() -> None:
    repository = FakeRepository()
    sink = KabuStationBarRepositorySink(
        repository=repository
    )

    sink(
        RealtimeBar(
            code="7203",
            started_at=datetime(
                2026,
                7,
                29,
                9,
                0,
                tzinfo=JST,
            ),
            ended_at=datetime(
                2026,
                7,
                29,
                9,
                5,
                tzinfo=JST,
            ),
            open_price=1000.0,
            high_price=1010.0,
            low_price=995.0,
            close_price=1005.0,
            volume=1234.0,
        )
    )

    prices, interval, source = repository.calls[0]
    assert interval == 5
    assert source == "kabu-station-realtime"
    assert prices[0].code == "7203"
    assert prices[0].volume == 1234

    status = sink.status()
    assert status.received_bar_count == 1
    assert status.saved_bar_count == 1
    assert status.last_error is None
