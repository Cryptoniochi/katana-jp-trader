"""Opening Range Breakout戦略のテスト。"""

from datetime import datetime, time

import pytest

from app.backtest.trade import ExitReason
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


def test_strategy_exits_at_take_profit() -> None:
    """利確価格へ到達したら利確する。"""

    prices = [
        create_price(
            9,
            0,
            open_price=1000,
            high=1005,
            low=995,
            close=1000,
        ),
        create_price(
            9,
            15,
            open_price=1000,
            high=1010,
            low=998,
            close=1005,
        ),
        create_price(
            9,
            20,
            open_price=1005,
            high=1020,
            low=1004,
            close=1010,
        ),
        create_price(
            9,
            25,
            open_price=1010,
            high=1035,
            low=1008,
            close=1030,
        ),
        create_price(
            14,
            50,
            open_price=1030,
            high=1040,
            low=1020,
            close=1035,
        ),
    ]

    strategy = OpeningRangeBreakoutStrategy(
        quantity=100,
        stop_loss_rate=0.01,
        take_profit_rate=0.02,
        force_exit_time=time(14, 50),
    )

    trade = strategy.generate_trades(prices)[0]

    assert trade.buy_price == pytest.approx(1010)
    assert trade.sell_price == pytest.approx(1030.2)
    assert trade.exit_at == datetime(2026, 7, 13, 9, 25)
    assert trade.exit_reason == ExitReason.TAKE_PROFIT


def test_strategy_exits_at_stop_loss() -> None:
    """損切り価格へ到達したら損切りする。"""

    prices = [
        create_price(
            9,
            0,
            open_price=1000,
            high=1005,
            low=995,
            close=1000,
        ),
        create_price(
            9,
            15,
            open_price=1000,
            high=1010,
            low=998,
            close=1005,
        ),
        create_price(
            9,
            20,
            open_price=1005,
            high=1020,
            low=1004,
            close=1010,
        ),
        create_price(
            9,
            25,
            open_price=1010,
            high=1012,
            low=995,
            close=1000,
        ),
        create_price(
            14,
            50,
            open_price=1000,
            high=1005,
            low=990,
            close=995,
        ),
    ]

    strategy = OpeningRangeBreakoutStrategy(
        quantity=100,
        stop_loss_rate=0.01,
        take_profit_rate=0.02,
        force_exit_time=time(14, 50),
    )

    trade = strategy.generate_trades(prices)[0]

    assert trade.buy_price == pytest.approx(1010)
    assert trade.sell_price == pytest.approx(999.9)
    assert trade.exit_at == datetime(2026, 7, 13, 9, 25)
    assert trade.exit_reason == ExitReason.STOP_LOSS


def test_strategy_prioritizes_stop_when_both_are_hit() -> None:
    """同じ足で利確と損切りに到達した場合は損切りを優先する。"""

    prices = [
        create_price(
            9,
            0,
            open_price=1000,
            high=1005,
            low=995,
            close=1000,
        ),
        create_price(
            9,
            15,
            open_price=1000,
            high=1010,
            low=998,
            close=1005,
        ),
        create_price(
            9,
            20,
            open_price=1005,
            high=1020,
            low=1004,
            close=1010,
        ),
        create_price(
            9,
            25,
            open_price=1010,
            high=1040,
            low=990,
            close=1020,
        ),
        create_price(
            14,
            50,
            open_price=1020,
            high=1025,
            low=1010,
            close=1015,
        ),
    ]

    strategy = OpeningRangeBreakoutStrategy(
        stop_loss_rate=0.01,
        take_profit_rate=0.02,
    )

    trade = strategy.generate_trades(prices)[0]

    assert trade.exit_reason == ExitReason.STOP_LOSS
    assert trade.sell_price == pytest.approx(999.9)


def test_strategy_exits_at_force_exit_time() -> None:
    """利確・損切りに到達しなければ指定時刻で決済する。"""

    prices = [
        create_price(
            9,
            0,
            open_price=1000,
            high=1005,
            low=995,
            close=1000,
        ),
        create_price(
            9,
            15,
            open_price=1000,
            high=1010,
            low=998,
            close=1005,
        ),
        create_price(
            9,
            20,
            open_price=1005,
            high=1020,
            low=1004,
            close=1010,
        ),
        create_price(
            10,
            0,
            open_price=1010,
            high=1015,
            low=1005,
            close=1012,
        ),
        create_price(
            14,
            50,
            open_price=1012,
            high=1018,
            low=1008,
            close=1015,
        ),
        create_price(
            15,
            30,
            open_price=1015,
            high=1020,
            low=1010,
            close=1018,
        ),
    ]

    strategy = OpeningRangeBreakoutStrategy(
        stop_loss_rate=0.05,
        take_profit_rate=0.05,
        force_exit_time=time(14, 50),
    )

    trade = strategy.generate_trades(prices)[0]

    assert trade.sell_price == pytest.approx(1015)
    assert trade.exit_at == datetime(2026, 7, 13, 14, 50)
    assert trade.exit_reason == ExitReason.TIME_EXIT


def test_strategy_returns_no_trade_without_breakout() -> None:
    """レンジ高値を突破しなければ取引しない。"""

    prices = [
        create_price(
            9,
            0,
            open_price=1000,
            high=1010,
            low=995,
            close=1005,
        ),
        create_price(
            9,
            15,
            open_price=1005,
            high=1020,
            low=1000,
            close=1015,
        ),
        create_price(
            9,
            20,
            open_price=1015,
            high=1020,
            low=1005,
            close=1010,
        ),
        create_price(
            14,
            50,
            open_price=1010,
            high=1018,
            low=1000,
            close=1005,
        ),
    ]

    strategy = OpeningRangeBreakoutStrategy()

    assert strategy.generate_trades(prices) == []


@pytest.mark.parametrize(
    ("field_name", "field_value", "message"),
    [
        ("quantity", 0, "数量"),
        ("stop_loss_rate", 0.0, "損切り"),
        ("take_profit_rate", -0.01, "利確"),
        ("commission", -1.0, "手数料"),
        ("slippage_rate", -0.01, "スリッページ"),
    ],
)
def test_strategy_rejects_invalid_parameters(
    field_name: str,
    field_value: int | float,
    message: str,
) -> None:
    """不正な戦略パラメータを拒否する。"""

    arguments = {
        "quantity": 100,
        field_name: field_value,
    }

    with pytest.raises(ValueError, match=message):
        OpeningRangeBreakoutStrategy(**arguments)
