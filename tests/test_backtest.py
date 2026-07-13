"""バックテストエンジンのテスト。"""

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


def test_backtest_engine_summarizes_trades() -> None:
    """勝ち・負け・引き分けを含む取引一覧を集計できる。"""

    trades = [
        Trade(
            code="7203",
            buy_price=3500.0,
            sell_price=3515.0,
            quantity=100,
        ),
        Trade(
            code="9984",
            buy_price=11000.0,
            sell_price=10950.0,
            quantity=100,
        ),
        Trade(
            code="6758",
            buy_price=4000.0,
            sell_price=4000.0,
            quantity=100,
        ),
    ]

    result = BacktestEngine().run(trades)

    assert result.total_profit == pytest.approx(-3500.0)
    assert result.trade_count == 3
    assert result.win_count == 1
    assert result.loss_count == 1
    assert result.breakeven_count == 1
    assert result.win_rate == pytest.approx(100 / 3)
    assert result.average_profit == pytest.approx(-3500 / 3)


def test_backtest_engine_accepts_empty_trade_list() -> None:
    """取引が0件でもエラーにせず、ゼロの結果を返す。"""

    result = BacktestEngine().run([])

    assert result.total_profit == 0
    assert result.trade_count == 0
    assert result.win_count == 0
    assert result.loss_count == 0
    assert result.breakeven_count == 0
    assert result.win_rate == 0
    assert result.average_profit == 0


def test_trade_rejects_zero_quantity() -> None:
    """数量0の取引を拒否する。"""

    with pytest.raises(ValueError, match="数量"):
        Trade(
            code="7203",
            buy_price=3500.0,
            sell_price=3515.0,
            quantity=0,
        )
