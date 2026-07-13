"""バックテストエンジンのテスト。"""

from math import inf

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.trade import Trade


def test_trade_calculates_profit_and_return_rate() -> None:
    """取引単体の損益と収益率を正しく計算できる。"""

    trade = Trade(
        code="7203",
        buy_price=3500.0,
        sell_price=3515.0,
        quantity=100,
    )

    assert trade.profit == pytest.approx(1500.0)
    assert trade.return_rate == pytest.approx(0.4285714286)


def test_backtest_engine_calculates_performance_metrics() -> None:
    """損益・勝率・PF・最大ドローダウンを計算できる。"""

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


def test_backtest_engine_counts_breakeven_trade() -> None:
    """損益0円の取引を引き分けとして数える。"""

    trades = [
        Trade(
            code="7203",
            buy_price=3500.0,
            sell_price=3500.0,
            quantity=100,
        )
    ]

    result = BacktestEngine().run(trades)

    assert result.trade_count == 1
    assert result.win_count == 0
    assert result.loss_count == 0
    assert result.breakeven_count == 1
    assert result.total_profit == 0
    assert result.profit_factor == 0
    assert result.max_drawdown == 0


def test_profit_factor_is_infinite_when_there_are_only_wins() -> None:
    """損失がなく利益だけある場合、PFを無限大とする。"""

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


def test_backtest_engine_accepts_empty_trade_list() -> None:
    """取引が0件でもゼロの結果を返す。"""

    result = BacktestEngine().run([])

    assert result.total_profit == 0
    assert result.gross_profit == 0
    assert result.gross_loss == 0
    assert result.max_drawdown == 0

    assert result.trade_count == 0
    assert result.win_count == 0
    assert result.loss_count == 0
    assert result.breakeven_count == 0

    assert result.win_rate == 0
    assert result.average_profit == 0
    assert result.expectancy == 0
    assert result.profit_factor == 0


def test_trade_rejects_zero_quantity() -> None:
    """数量0の取引を拒否する。"""

    with pytest.raises(ValueError, match="数量"):
        Trade(
            code="7203",
            buy_price=3500.0,
            sell_price=3515.0,
            quantity=0,
        )
