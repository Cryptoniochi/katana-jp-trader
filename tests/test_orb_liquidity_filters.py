"""ORB株価帯・売買代金フィルターのテスト。"""

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
    close: float,
    high: float,
    low: float,
    volume: int,
) -> StockPrice:
    """流動性フィルター用の5分足を作成する。"""

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


def create_prices(
    *,
    price_level: float = 1000.0,
    opening_volume: int = 100_000,
    breakout_volume: int = 200_000,
) -> list[StockPrice]:
    """通常のORBブレイクが発生するデータを作成する。"""

    return [
        create_price(
            9,
            0,
            close=price_level,
            high=price_level + 5,
            low=price_level - 5,
            volume=opening_volume,
        ),
        create_price(
            9,
            15,
            close=price_level + 5,
            high=price_level + 10,
            low=price_level - 2,
            volume=opening_volume,
        ),
        create_price(
            9,
            20,
            close=price_level + 10,
            high=price_level + 20,
            low=price_level + 4,
            volume=breakout_volume,
        ),
        create_price(
            14,
            50,
            close=price_level + 20,
            high=price_level + 25,
            low=price_level + 8,
            volume=300_000,
        ),
    ]


def test_strategy_accepts_price_inside_range() -> None:
    """エントリー価格が指定株価帯なら取引する。"""

    strategy = OpeningRangeBreakoutStrategy(
        min_price=500.0,
        max_price=2000.0,
    )

    trades = strategy.generate_trades(create_prices(price_level=1000.0))

    assert len(trades) == 1


def test_strategy_rejects_price_below_minimum() -> None:
    """最低株価を下回る銘柄を除外する。"""

    strategy = OpeningRangeBreakoutStrategy(
        min_price=500.0,
    )

    trades = strategy.generate_trades(create_prices(price_level=300.0))

    assert trades == []


def test_strategy_rejects_price_above_maximum() -> None:
    """最高株価を上回る銘柄を除外する。"""

    strategy = OpeningRangeBreakoutStrategy(
        max_price=2000.0,
    )

    trades = strategy.generate_trades(create_prices(price_level=3000.0))

    assert trades == []


def test_strategy_accepts_opening_turnover() -> None:
    """寄り付き売買代金が基準以上なら取引する。"""

    strategy = OpeningRangeBreakoutStrategy(
        min_opening_range_turnover=150_000_000.0,
    )

    trades = strategy.generate_trades(
        create_prices(
            price_level=1000.0,
            opening_volume=100_000,
        )
    )

    assert len(trades) == 1


def test_strategy_rejects_low_opening_turnover() -> None:
    """寄り付き売買代金が不足する銘柄を除外する。"""

    strategy = OpeningRangeBreakoutStrategy(
        min_opening_range_turnover=300_000_000.0,
    )

    trades = strategy.generate_trades(
        create_prices(
            price_level=1000.0,
            opening_volume=100_000,
        )
    )

    assert trades == []


def test_strategy_accepts_breakout_turnover() -> None:
    """ブレイク足売買代金が基準以上なら取引する。"""

    strategy = OpeningRangeBreakoutStrategy(
        min_breakout_turnover=150_000_000.0,
    )

    trades = strategy.generate_trades(
        create_prices(
            price_level=1000.0,
            breakout_volume=200_000,
        )
    )

    assert len(trades) == 1


def test_strategy_rejects_low_breakout_turnover() -> None:
    """ブレイク足売買代金が不足する銘柄を除外する。"""

    strategy = OpeningRangeBreakoutStrategy(
        min_breakout_turnover=300_000_000.0,
    )

    trades = strategy.generate_trades(
        create_prices(
            price_level=1000.0,
            breakout_volume=200_000,
        )
    )

    assert trades == []


@pytest.mark.parametrize(
    ("field_name", "field_value", "message"),
    [
        ("min_price", 0.0, "最低株価"),
        ("max_price", -1.0, "最高株価"),
        (
            "min_opening_range_turnover",
            -1.0,
            "オープニングレンジ売買代金",
        ),
        (
            "min_breakout_turnover",
            -1.0,
            "ブレイク足売買代金",
        ),
    ],
)
def test_strategy_rejects_invalid_liquidity_parameters(
    field_name: str,
    field_value: float,
    message: str,
) -> None:
    """不正な株価帯・売買代金条件を拒否する。"""

    with pytest.raises(ValueError, match=message):
        OpeningRangeBreakoutStrategy(**{field_name: field_value})


def test_strategy_rejects_reversed_price_range() -> None:
    """最低株価が最高株価を超える条件を拒否する。"""

    with pytest.raises(ValueError, match="最低株価"):
        OpeningRangeBreakoutStrategy(
            min_price=2000.0,
            max_price=1000.0,
        )
