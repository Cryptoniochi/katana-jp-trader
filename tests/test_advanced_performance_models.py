"""高度Performance Analyticsモデルのテスト。"""

import pytest

from app.backtest.advanced_performance_models import (
    AdvancedPerformanceAnalytics,
    PerformanceBreakdown,
)


def test_breakdown_validates_counts() -> None:
    with pytest.raises(
        ValueError,
        match="一致しません",
    ):
        PerformanceBreakdown(
            key="7203",
            trade_count=2,
            winning_trade_count=2,
            losing_trade_count=1,
            flat_trade_count=0,
            gross_profit=1000.0,
            gross_loss=500.0,
            net_profit_loss=500.0,
            win_rate=1.0,
            profit_factor=2.0,
            average_profit_loss=250.0,
        )


def test_empty_analytics_is_valid() -> None:
    analytics = AdvancedPerformanceAnalytics(
        trade_count=0,
        average_trade_return=None,
        trade_return_volatility=None,
        trade_sharpe_ratio=None,
        downside_deviation=None,
        payoff_ratio=None,
        average_holding_seconds=None,
        maximum_holding_seconds=None,
        monthly=(),
        by_code=(),
        by_entry_hour=(),
        by_exit_reason=(),
    )

    assert analytics.trade_count == 0
    assert analytics.monthly == ()
