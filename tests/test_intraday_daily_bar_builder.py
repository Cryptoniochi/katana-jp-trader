"""IntradayDailyBarBuilderのテスト。"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.database import initialize_database
from app.market.bar_repository import (
    MarketBarRepository,
)
from app.market.intraday_daily_bar_builder import (
    DAILY_INTERVAL_MINUTES,
    IntradayDailyBarBuilder,
)
from app.market.models import StockPrice


JST = ZoneInfo("Asia/Tokyo")


def price(
    day: int,
    hour: int,
    minute: int,
    *,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    volume: int,
) -> StockPrice:
    return StockPrice(
        code="7203",
        datetime=datetime(
            2026,
            7,
            day,
            hour,
            minute,
            tzinfo=JST,
        ),
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume,
    )


def create_repository(
    tmp_path: Path,
) -> MarketBarRepository:
    database_path = tmp_path / "katana.db"
    initialize_database(database_path)
    return MarketBarRepository(database_path)


def test_builder_aggregates_five_minute_bars(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)
    repository.save_all(
        [
            price(
                30,
                9,
                0,
                open_price=1000,
                high_price=1010,
                low_price=995,
                close_price=1005,
                volume=100,
            ),
            price(
                30,
                9,
                5,
                open_price=1005,
                high_price=1020,
                low_price=1000,
                close_price=1015,
                volume=200,
            ),
            price(
                31,
                9,
                0,
                open_price=1020,
                high_price=1030,
                low_price=1010,
                close_price=1025,
                volume=300,
            ),
        ],
        interval_minutes=5,
        data_source="test",
    )

    result = IntradayDailyBarBuilder(
        repository=repository
    ).build(
        codes=("7203",)
    )

    assert result.source_bar_count == 3
    assert result.daily_bar_count == 2
    assert result.saved_bar_count == 2

    daily = repository.read(
        code="7203",
        interval_minutes=DAILY_INTERVAL_MINUTES,
    )

    assert len(daily) == 2
    assert daily[0].open == 1000
    assert daily[0].high == 1020
    assert daily[0].low == 995
    assert daily[0].close == 1015
    assert daily[0].volume == 300


def test_builder_upserts_existing_daily_bar(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)
    repository.save_all(
        [
            price(
                30,
                9,
                0,
                open_price=1000,
                high_price=1010,
                low_price=995,
                close_price=1005,
                volume=100,
            ),
        ],
        interval_minutes=5,
        data_source="test",
    )

    builder = IntradayDailyBarBuilder(
        repository=repository
    )

    builder.build(codes=("7203",))
    builder.build(codes=("7203",))

    assert repository.count(
        code="7203",
        interval_minutes=DAILY_INTERVAL_MINUTES,
    ) == 1


def test_builder_skips_code_without_intraday_bars(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    result = IntradayDailyBarBuilder(
        repository=repository
    ).build(
        codes=("7203",)
    )

    assert result.source_bar_count == 0
    assert result.daily_bar_count == 0
    assert result.saved_bar_count == 0
