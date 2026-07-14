"""ORB出来高フィルターのテスト。"""

from datetime import datetime

import pytest

from app.market.models import StockPrice
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


def create_price(
    hour: int,
    minute: int,
    *,
    high: float,
    low: float,
    close: float,
    volume: int,
) -> StockPrice:
    """出来高フィルターテスト用の5分足を作る。"""

    return StockPrice(
        code="7203",
        datetime=datetime(
            2026,
            7,
            13,
            hour,
            minute,
        ),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def create_breakout_prices(
    breakout_volume: int = 200_000,
) -> list[StockPrice]:
    """通常のORBブレイクが発生する株価一覧を作る。"""

    return [
        create_price(
            9,
            0,
            high=1005,
            low=995,
            close=1000,
            volume=100_000,
        ),
        create_price(
            9,
            15,
            high=1010,
            low=998,
            close=1005,
            volume=120_000,
        ),
        create_price(
            9,
            20,
            high=1020,
            low=1004,
            close=1010,
            volume=breakout_volume,
        ),
        create_price(
            14,
            50,
            high=1025,
            low=1008,
            close=1020,
            volume=300_000,
        ),
    ]


def test_strategy_accepts_sufficient_opening_volume() -> None:
    """オープニングレンジ累計出来高が基準以上なら取引する。"""

    strategy = OpeningRangeBreakoutStrategy(
        min_opening_range_volume=200_000,
    )

    trades = strategy.generate_trades(create_breakout_prices())

    assert len(trades) == 1


def test_strategy_rejects_low_opening_volume() -> None:
    """オープニングレンジ累計出来高が不足すれば取引しない。"""

    strategy = OpeningRangeBreakoutStrategy(
        min_opening_range_volume=300_000,
    )

    trades = strategy.generate_trades(create_breakout_prices())

    assert trades == []


def test_strategy_rejects_low_breakout_volume() -> None:
    """ブレイク足の出来高が最低値未満なら取引しない。"""

    strategy = OpeningRangeBreakoutStrategy(
        min_breakout_volume=250_000,
    )

    trades = strategy.generate_trades(
        create_breakout_prices(
            breakout_volume=200_000,
        )
    )

    assert trades == []


def test_strategy_accepts_breakout_volume_ratio() -> None:
    """ブレイク出来高倍率が基準以上なら取引する。"""

    strategy = OpeningRangeBreakoutStrategy(
        breakout_volume_ratio=1.5,
    )

    trades = strategy.generate_trades(
        create_breakout_prices(
            breakout_volume=200_000,
        )
    )

    assert len(trades) == 1


def test_strategy_rejects_low_breakout_volume_ratio() -> None:
    """ブレイク出来高倍率が不足すれば取引しない。"""

    strategy = OpeningRangeBreakoutStrategy(
        breakout_volume_ratio=2.0,
    )

    trades = strategy.generate_trades(
        create_breakout_prices(
            breakout_volume=200_000,
        )
    )

    assert trades == []


def test_strategy_uses_later_breakout_with_enough_volume() -> None:
    """最初の突破足が出来高不足なら次の有効な突破足を使う。"""

    prices = [
        create_price(
            9,
            0,
            high=1005,
            low=995,
            close=1000,
            volume=100_000,
        ),
        create_price(
            9,
            15,
            high=1010,
            low=998,
            close=1005,
            volume=100_000,
        ),
        create_price(
            9,
            20,
            high=1020,
            low=1004,
            close=1010,
            volume=80_000,
        ),
        create_price(
            9,
            25,
            high=1025,
            low=1008,
            close=1015,
            volume=200_000,
        ),
        create_price(
            14,
            50,
            high=1030,
            low=1010,
            close=1020,
            volume=300_000,
        ),
    ]

    strategy = OpeningRangeBreakoutStrategy(
        min_breakout_volume=150_000,
    )

    trades = strategy.generate_trades(prices)

    assert len(trades) == 1
    assert trades[0].buy_price == pytest.approx(1015)
    assert trades[0].entry_at == datetime(
        2026,
        7,
        13,
        9,
        25,
    )


@pytest.mark.parametrize(
    ("field_name", "field_value", "message"),
    [
        (
            "min_opening_range_volume",
            -1,
            "オープニングレンジ出来高",
        ),
        (
            "min_breakout_volume",
            -1,
            "ブレイク足出来高",
        ),
        (
            "breakout_volume_ratio",
            0.0,
            "出来高倍率",
        ),
    ],
)
def test_strategy_rejects_invalid_volume_parameters(
    field_name: str,
    field_value: int | float,
    message: str,
) -> None:
    """不正な出来高条件を拒否する。"""

    arguments = {
        field_name: field_value,
    }

    with pytest.raises(ValueError, match=message):
        OpeningRangeBreakoutStrategy(**arguments)
