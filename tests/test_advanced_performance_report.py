"""高度Performance Analytics JSON変換のテスト。"""

import json

from app.backtest.advanced_performance_models import (
    AdvancedPerformanceAnalytics,
    PerformanceBreakdown,
)
from app.backtest.advanced_performance_report import (
    advanced_performance_analytics_to_dict,
)


def test_analytics_report_is_json_compatible() -> None:
    breakdown = PerformanceBreakdown(
        key="7203",
        trade_count=2,
        winning_trade_count=1,
        losing_trade_count=1,
        flat_trade_count=0,
        gross_profit=1000.0,
        gross_loss=500.0,
        net_profit_loss=500.0,
        win_rate=0.5,
        profit_factor=2.0,
        average_profit_loss=250.0,
    )
    analytics = AdvancedPerformanceAnalytics(
        trade_count=2,
        average_trade_return=0.0025,
        trade_return_volatility=0.0075,
        trade_sharpe_ratio=0.4714,
        downside_deviation=0.0035,
        payoff_ratio=2.0,
        average_holding_seconds=300.0,
        maximum_holding_seconds=300.0,
        monthly=(),
        by_code=(breakdown,),
        by_entry_hour=(),
        by_exit_reason=(),
    )

    payload = advanced_performance_analytics_to_dict(
        analytics
    )
    serialized = json.dumps(payload)

    assert payload["trade_count"] == 2
    assert payload["payoff_ratio"] == 2.0
    assert payload["by_code"][0]["key"] == "7203"
    assert payload["by_code"][0]["profit_factor"] == 2.0
    assert "7203" in serialized
