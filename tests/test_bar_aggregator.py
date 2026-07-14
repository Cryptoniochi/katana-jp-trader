"""ローソク足集約機能のテスト。"""

from datetime import datetime

import pytest

from app.market.bar_aggregator import StockPriceAggregator
from app.market.models import StockPrice


def create_price(
    time_text: str,
    *,
    code: str = "7203",
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: int,
) -> StockPrice:
    """テスト用の1分足を作成する。"""

    return StockPrice(
        code=code,
        datetime=datetime.strptime(
            f"2026-07-13 {time_text}",
            "%Y-%m-%d %H:%M",
        ),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def test_aggregator_creates_five_minute_bar() -> None:
    """5本の1分足を1本の5分足へ集約できる。"""

    prices = [
        create_price(
            "09:00",
            open_price=1000,
            high=1005,
            low=998,
            close=1002,
            volume=100,
        ),
        create_price(
            "09:01",
            open_price=1002,
            high=1008,
            low=1001,
            close=1006,
            volume=200,
        ),
        create_price(
            "09:02",
            open_price=1006,
            high=1010,
            low=1004,
            close=1005,
            volume=300,
        ),
        create_price(
            "09:03",
            open_price=1005,
            high=1007,
            low=997,
            close=999,
            volume=400,
        ),
        create_price(
            "09:04",
            open_price=999,
            high=1004,
            low=996,
            close=1003,
            volume=500,
        ),
    ]

    result = StockPriceAggregator().aggregate_to_five_minutes(prices)

    assert len(result) == 1

    bar = result[0]

    assert bar.code == "7203"
    assert bar.datetime == datetime(
        2026,
        7,
        13,
        9,
        0,
    )
    assert bar.open == pytest.approx(1000)
    assert bar.high == pytest.approx(1010)
    assert bar.low == pytest.approx(996)
    assert bar.close == pytest.approx(1003)
    assert bar.volume == 1500


def test_aggregator_creates_separate_buckets() -> None:
    """異なる5分区間を別々の足へ集約する。"""

    prices = [
        create_price(
            "09:04",
            open_price=1000,
            high=1005,
            low=995,
            close=1002,
            volume=100,
        ),
        create_price(
            "09:05",
            open_price=1002,
            high=1010,
            low=1000,
            close=1008,
            volume=200,
        ),
    ]

    result = StockPriceAggregator().aggregate_to_five_minutes(prices)

    assert len(result) == 2
    assert result[0].datetime.minute == 0
    assert result[1].datetime.minute == 5


def test_aggregator_accepts_missing_minutes() -> None:
    """約定のない分が欠けていても存在する足で集約する。"""

    prices = [
        create_price(
            "09:00",
            open_price=1000,
            high=1005,
            low=995,
            close=1002,
            volume=100,
        ),
        create_price(
            "09:03",
            open_price=1002,
            high=1008,
            low=1000,
            close=1007,
            volume=300,
        ),
    ]

    result = StockPriceAggregator().aggregate_to_five_minutes(prices)

    assert len(result) == 1
    assert result[0].open == pytest.approx(1000)
    assert result[0].close == pytest.approx(1007)
    assert result[0].volume == 400


def test_aggregator_does_not_cross_lunch_break() -> None:
    """前場と後場を同じ足へまとめない。"""

    prices = [
        create_price(
            "11:30",
            open_price=1000,
            high=1005,
            low=995,
            close=1002,
            volume=100,
        ),
        create_price(
            "12:30",
            open_price=1010,
            high=1015,
            low=1005,
            close=1012,
            volume=200,
        ),
    ]

    result = StockPriceAggregator().aggregate_to_five_minutes(prices)

    assert len(result) == 2
    assert result[0].datetime.time().isoformat() == ("11:30:00")
    assert result[1].datetime.time().isoformat() == ("12:30:00")


def test_aggregator_separates_stock_codes() -> None:
    """同時刻でも異なる銘柄は別々に集約する。"""

    prices = [
        create_price(
            "09:00",
            code="7203",
            open_price=1000,
            high=1005,
            low=995,
            close=1002,
            volume=100,
        ),
        create_price(
            "09:00",
            code="9984",
            open_price=2000,
            high=2010,
            low=1990,
            close=2005,
            volume=200,
        ),
    ]

    result = StockPriceAggregator().aggregate_to_five_minutes(prices)

    assert len(result) == 2
    assert {price.code for price in result} == {
        "7203",
        "9984",
    }


def test_aggregator_sorts_unsorted_input() -> None:
    """入力順に関係なく始値と終値を正しく決める。"""

    prices = [
        create_price(
            "09:04",
            open_price=1004,
            high=1008,
            low=1002,
            close=1007,
            volume=200,
        ),
        create_price(
            "09:00",
            open_price=1000,
            high=1005,
            low=998,
            close=1004,
            volume=100,
        ),
    ]

    result = StockPriceAggregator().aggregate_to_five_minutes(prices)

    assert result[0].open == pytest.approx(1000)
    assert result[0].close == pytest.approx(1007)


def test_aggregator_returns_empty_list() -> None:
    """入力が空なら空の一覧を返す。"""

    result = StockPriceAggregator().aggregate_to_five_minutes([])

    assert result == []


@pytest.mark.parametrize(
    "interval_minutes",
    [0, -1, 61],
)
def test_aggregator_rejects_invalid_interval(
    interval_minutes: int,
) -> None:
    """不正な集約間隔を拒否する。"""

    with pytest.raises(
        ValueError,
        match="集約間隔",
    ):
        StockPriceAggregator().aggregate(
            prices=[],
            interval_minutes=interval_minutes,
        )
