"""Opening Range Breakout戦略のテスト。"""

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
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> StockPrice:
    """テスト用の7203の5分足を作成する。"""

    return StockPrice(
        code="7203",
        datetime=datetime(
            2026,
            7,
            13,
            hour,
            minute,
        ),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=100_000,
    )


def test_strategy_generates_trade_after_breakout() -> None:
    """オープニングレンジ高値突破後に取引を生成する。"""

    prices = [
        create_price(
            9,
            0,
            open_price=3500,
            high=3510,
            low=3495,
            close=3505,
        ),
        create_price(
            9,
            5,
            open_price=3505,
            high=3515,
            low=3500,
            close=3510,
        ),
        create_price(
            9,
            10,
            open_price=3510,
            high=3520,
            low=3505,
            close=3515,
        ),
        create_price(
            9,
            15,
            open_price=3515,
            high=3525,
            low=3510,
            close=3520,
        ),
        create_price(
            9,
            20,
            open_price=3520,
            high=3524,
            low=3515,
            close=3518,
        ),
        create_price(
            9,
            25,
            open_price=3518,
            high=3535,
            low=3518,
            close=3530,
        ),
        create_price(
            15,
            30,
            open_price=3540,
            high=3550,
            low=3535,
            close=3545,
        ),
    ]

    strategy = OpeningRangeBreakoutStrategy(quantity=100)
    trades = strategy.generate_trades(prices)

    assert len(trades) == 1

    trade = trades[0]

    assert trade.code == "7203"
    assert trade.buy_price == 3530
    assert trade.sell_price == 3545
    assert trade.quantity == 100
    assert trade.profit == pytest.approx(1500)


def test_strategy_returns_no_trade_without_breakout() -> None:
    """レンジ高値を突破しなければ取引しない。"""

    prices = [
        create_price(
            9,
            0,
            open_price=3500,
            high=3520,
            low=3490,
            close=3510,
        ),
        create_price(
            9,
            15,
            open_price=3510,
            high=3525,
            low=3505,
            close=3520,
        ),
        create_price(
            9,
            20,
            open_price=3520,
            high=3525,
            low=3500,
            close=3510,
        ),
        create_price(
            15,
            30,
            open_price=3510,
            high=3520,
            low=3495,
            close=3500,
        ),
    ]

    strategy = OpeningRangeBreakoutStrategy()

    assert strategy.generate_trades(prices) == []


def test_strategy_uses_first_breakout_bar() -> None:
    """複数回の突破があっても最初の突破足を使う。"""

    prices = [
        create_price(
            9,
            0,
            open_price=3500,
            high=3510,
            low=3490,
            close=3505,
        ),
        create_price(
            9,
            15,
            open_price=3505,
            high=3520,
            low=3500,
            close=3515,
        ),
        create_price(
            9,
            20,
            open_price=3515,
            high=3530,
            low=3510,
            close=3525,
        ),
        create_price(
            9,
            25,
            open_price=3525,
            high=3540,
            low=3520,
            close=3535,
        ),
        create_price(
            15,
            30,
            open_price=3535,
            high=3545,
            low=3525,
            close=3530,
        ),
    ]

    trades = OpeningRangeBreakoutStrategy(quantity=100).generate_trades(prices)

    assert len(trades) == 1
    assert trades[0].buy_price == 3525
    assert trades[0].sell_price == 3530
    assert trades[0].profit == pytest.approx(500)


def test_strategy_applies_transaction_costs() -> None:
    """取引コストを生成した取引へ引き継ぐ。"""

    prices = [
        create_price(
            9,
            0,
            open_price=3500,
            high=3510,
            low=3490,
            close=3505,
        ),
        create_price(
            9,
            15,
            open_price=3505,
            high=3520,
            low=3500,
            close=3515,
        ),
        create_price(
            9,
            20,
            open_price=3515,
            high=3530,
            low=3510,
            close=3525,
        ),
        create_price(
            15,
            30,
            open_price=3530,
            high=3540,
            low=3520,
            close=3535,
        ),
    ]

    strategy = OpeningRangeBreakoutStrategy(
        quantity=100,
        commission=200,
        slippage_rate=0.0005,
    )

    trade = strategy.generate_trades(prices)[0]

    assert trade.commission == 200
    assert trade.slippage_rate == pytest.approx(0.0005)
    assert trade.profit < trade.gross_profit


def test_strategy_rejects_invalid_quantity() -> None:
    """数量0を拒否する。"""

    with pytest.raises(ValueError, match="数量"):
        OpeningRangeBreakoutStrategy(quantity=0)
