"""バックテストエンジンと取引コストのテスト。"""

from math import inf

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.trade import Trade


def test_trade_calculates_profit_without_costs() -> None:
    """コストなしの取引損益を計算できる。"""

    trade = Trade(
        code="7203",
        buy_price=3500.0,
        sell_price=3515.0,
        quantity=100,
    )

    assert trade.gross_profit == pytest.approx(1500.0)
    assert trade.total_cost == pytest.approx(0.0)
    assert trade.profit == pytest.approx(1500.0)
    assert trade.return_rate == pytest.approx(0.4285714286)


def test_trade_deducts_commission_and_slippage() -> None:
    """手数料とスリッページを純損益から控除する。"""

    trade = Trade(
        code="7203",
        buy_price=3500.0,
        sell_price=3515.0,
        quantity=100,
        commission=200.0,
        slippage_rate=0.0005,
    )

    expected_slippage = 3500.0 * 100 * 0.0005 + 3515.0 * 100 * 0.0005

    assert trade.gross_profit == pytest.approx(1500.0)
    assert trade.slippage_cost == pytest.approx(expected_slippage)
    assert trade.total_cost == pytest.approx(200.0 + expected_slippage)
    assert trade.profit == pytest.approx(1500.0 - 200.0 - expected_slippage)


def test_costs_can_turn_gross_win_into_net_loss() -> None:
    """小さな利益がコスト控除後に損失になる。"""

    trade = Trade(
        code="7203",
        buy_price=3500.0,
        sell_price=3502.0,
        quantity=100,
        commission=200.0,
        slippage_rate=0.0005,
    )

    assert trade.gross_profit == pytest.approx(200.0)
    assert trade.profit < 0


def test_backtest_engine_calculates_metrics() -> None:
    """複数取引の主要指標を計算できる。"""

    trades = [
        Trade(
            code="7203",
            buy_price=1000.0,
            sell_price=1050.0,
            quantity=100,
        ),
        Trade(
            code="9984",
            buy_price=2000.0,
            sell_price=1980.0,
            quantity=100,
        ),
        Trade(
            code="6758",
            buy_price=3000.0,
            sell_price=2960.0,
            quantity=100,
        ),
        Trade(
            code="8306",
            buy_price=1500.0,
            sell_price=1530.0,
            quantity=100,
        ),
    ]

    result = BacktestEngine().run(trades)

    assert result.total_profit == pytest.approx(2000.0)
    assert result.gross_profit == pytest.approx(8000.0)
    assert result.gross_loss == pytest.approx(-6000.0)
    assert result.trade_count == 4
    assert result.win_count == 2
    assert result.loss_count == 2
    assert result.breakeven_count == 0
    assert result.win_rate == pytest.approx(50.0)
    assert result.average_profit == pytest.approx(500.0)
    assert result.expectancy == pytest.approx(500.0)
    assert result.profit_factor == pytest.approx(8 / 6)
    assert result.max_drawdown == pytest.approx(6000.0)


def test_profit_factor_is_infinite_for_only_wins() -> None:
    """利益だけで損失がない場合はPFを無限大とする。"""

    trades = [
        Trade(
            code="7203",
            buy_price=3500.0,
            sell_price=3515.0,
            quantity=100,
        )
    ]

    result = BacktestEngine().run(trades)

    assert result.profit_factor == inf


def test_backtest_engine_accepts_empty_list() -> None:
    """取引が0件でもゼロの結果を返す。"""

    result = BacktestEngine().run([])

    assert result.total_profit == 0
    assert result.gross_profit == 0
    assert result.gross_loss == 0
    assert result.max_drawdown == 0
    assert result.trade_count == 0
    assert result.win_rate == 0
    assert result.profit_factor == 0


@pytest.mark.parametrize(
    ("field_name", "field_value", "message"),
    [
        ("commission", -1.0, "手数料"),
        ("slippage_rate", -0.01, "スリッページ"),
    ],
)
def test_trade_rejects_negative_costs(
    field_name: str,
    field_value: float,
    message: str,
) -> None:
    """負の手数料またはスリッページ率を拒否する。"""

    arguments = {
        "code": "7203",
        "buy_price": 3500.0,
        "sell_price": 3515.0,
        "quantity": 100,
        field_name: field_value,
    }

    with pytest.raises(ValueError, match=message):
        Trade(**arguments)
