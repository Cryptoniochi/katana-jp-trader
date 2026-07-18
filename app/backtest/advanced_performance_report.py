"""高度なPerformance AnalyticsをJSON互換辞書へ変換する。"""

from __future__ import annotations

from typing import Any

from app.backtest.advanced_performance_models import (
    AdvancedPerformanceAnalytics,
    PerformanceBreakdown,
)


def _breakdown_to_dict(
    breakdown: PerformanceBreakdown,
) -> dict[str, Any]:
    """1件の内訳を辞書へ変換する。"""

    return {
        "key": breakdown.key,
        "trade_count": breakdown.trade_count,
        "winning_trade_count": (
            breakdown.winning_trade_count
        ),
        "losing_trade_count": (
            breakdown.losing_trade_count
        ),
        "flat_trade_count": (
            breakdown.flat_trade_count
        ),
        "gross_profit": breakdown.gross_profit,
        "gross_loss": breakdown.gross_loss,
        "net_profit_loss": breakdown.net_profit_loss,
        "win_rate": breakdown.win_rate,
        "profit_factor": breakdown.profit_factor,
        "average_profit_loss": (
            breakdown.average_profit_loss
        ),
    }


def advanced_performance_analytics_to_dict(
    analytics: AdvancedPerformanceAnalytics,
) -> dict[str, Any]:
    """高度分析結果を辞書へ変換する。"""

    return {
        "trade_count": analytics.trade_count,
        "average_trade_return": (
            analytics.average_trade_return
        ),
        "trade_return_volatility": (
            analytics.trade_return_volatility
        ),
        "trade_sharpe_ratio": (
            analytics.trade_sharpe_ratio
        ),
        "downside_deviation": (
            analytics.downside_deviation
        ),
        "payoff_ratio": analytics.payoff_ratio,
        "average_holding_seconds": (
            analytics.average_holding_seconds
        ),
        "maximum_holding_seconds": (
            analytics.maximum_holding_seconds
        ),
        "monthly": [
            _breakdown_to_dict(item)
            for item in analytics.monthly
        ],
        "by_code": [
            _breakdown_to_dict(item)
            for item in analytics.by_code
        ],
        "by_entry_hour": [
            _breakdown_to_dict(item)
            for item in analytics.by_entry_hour
        ],
        "by_exit_reason": [
            _breakdown_to_dict(item)
            for item in analytics.by_exit_reason
        ],
    }
