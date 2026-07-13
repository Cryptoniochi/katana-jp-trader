"""始値買い・終値売り戦略のテスト。"""

from datetime import datetime

import pytest

from app.market.models import StockPrice
from app.strategy.buy_open_sell_close import BuyOpenSellCloseStrategy


def test_strategy_generates_one_trade_from_same_day_prices() -> None:
    """同一銘柄・同一日の足から1件の取引を生成できる。"""

    prices = [
        StockPrice(
            code="7203",
            datetime=datetime(2026, 7, 13, 9, 5),
            open=3510.0,
            high=3530.0,
            low=3505.0,
            close=3520.0,
            volume=2_000,
        ),
        StockPrice(
            code="7203",
            datetime=datetime(2026, 7, 13, 9, 0),
            open=3500.0,
            high=3520.0,
            low=3490.0,
            close=3510.0,
            volume=1_000,
        ),
        StockPrice(
            code="7203",
            datetime=datetime(2026, 7, 13, 15, 30),
            open=3530.0,
            high=3540.0,
            low=3520.0,
            close=3535.0,
            volume=3_000,
        ),
    ]

    strategy = BuyOpenSellCloseStrategy(quantity=100)
    trades = strategy.generate_trades(prices)

    assert len(trades) == 1

    trade = trades[0]

    assert trade.code == "7203"
    assert trade.buy_price == 3500.0
    assert trade.sell_price == 3535.0
    assert trade.quantity == 100
    assert trade.profit == pytest.approx(3500.0)


def test_strategy_separates_codes_and_dates() -> None:
    """銘柄と日付が異なるデータを別々の取引にする。"""

    prices = [
        StockPrice(
            code="7203",
            datetime=datetime(2026, 7, 13, 9, 0),
            open=3500.0,
            high=3520.0,
            low=3490.0,
            close=3510.0,
            volume=1_000,
        ),
        StockPrice(
            code="7203",
            datetime=datetime(2026, 7, 13, 15, 30),
            open=3510.0,
            high=3540.0,
            low=3500.0,
            close=3530.0,
            volume=2_000,
        ),
        StockPrice(
            code="7203",
            datetime=datetime(2026, 7, 14, 9, 0),
            open=3540.0,
            high=3550.0,
            low=3520.0,
            close=3525.0,
            volume=1_500,
        ),
        StockPrice(
            code="9984",
            datetime=datetime(2026, 7, 13, 9, 0),
            open=11000.0,
            high=11100.0,
            low=10900.0,
            close=10950.0,
            volume=5_000,
        ),
    ]

    strategy = BuyOpenSellCloseStrategy(quantity=100)
    trades = strategy.generate_trades(prices)

    assert len(trades) == 3

    profits = sorted(trade.profit for trade in trades)

    assert profits == pytest.approx(
        [
            -5000.0,
            -1500.0,
            3000.0,
        ]
    )


def test_strategy_accepts_empty_price_list() -> None:
    """株価データが0件なら空の取引一覧を返す。"""

    strategy = BuyOpenSellCloseStrategy(quantity=100)

    assert strategy.generate_trades([]) == []


def test_strategy_rejects_zero_quantity() -> None:
    """数量0を拒否する。"""

    with pytest.raises(ValueError, match="数量"):
        BuyOpenSellCloseStrategy(quantity=0)
