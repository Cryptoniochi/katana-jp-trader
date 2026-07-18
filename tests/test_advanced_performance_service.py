"""AdvancedPerformanceAnalyticsServiceのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.backtest.advanced_performance_service import (
    AdvancedPerformanceAnalyticsService,
)
from app.backtest.trade_report_models import (
    BacktestTradeReport,
    CompletedBacktestTrade,
)


BASE = datetime(
    2026,
    7,
    1,
    0,
    20,
    tzinfo=timezone.utc,
)


def trade(
    *,
    sequence: int,
    code: str,
    profit: float,
    entered_at: datetime,
    exit_reason: str | None,
) -> CompletedBacktestTrade:
    entry_price = 1000.0
    quantity = 100
    exit_price = entry_price + profit / quantity

    return CompletedBacktestTrade(
        trade_id=f"trade-{sequence}",
        code=code,
        quantity=quantity,
        entry_execution_id=f"buy-{sequence}",
        exit_execution_id=f"sell-{sequence}",
        entry_signal_id=f"signal-buy-{sequence}",
        exit_signal_id=f"signal-sell-{sequence}",
        entered_at=entered_at,
        exited_at=entered_at + timedelta(minutes=5),
        entry_price=entry_price,
        exit_price=exit_price,
        entry_commission=0.0,
        exit_commission=0.0,
        entry_slippage=0.0,
        exit_slippage=0.0,
        exit_reason=exit_reason,
    )


def report() -> BacktestTradeReport:
    return BacktestTradeReport(
        trades=(
            trade(
                sequence=1,
                code="7203",
                profit=1000.0,
                entered_at=BASE,
                exit_reason="take_profit",
            ),
            trade(
                sequence=2,
                code="7203",
                profit=-500.0,
                entered_at=BASE.replace(hour=1),
                exit_reason="stop_loss",
            ),
            trade(
                sequence=3,
                code="6758",
                profit=2000.0,
                entered_at=BASE.replace(month=8),
                exit_reason=None,
            ),
        ),
        unmatched_buy_quantity=0,
        unmatched_sell_quantity=0,
    )


def test_service_calculates_advanced_metrics() -> None:
    analytics = (
        AdvancedPerformanceAnalyticsService()
        .create(report())
    )

    assert analytics.trade_count == 3
    assert analytics.average_trade_return == pytest.approx(
        (0.01 - 0.005 + 0.02) / 3
    )
    assert analytics.trade_return_volatility is not None
    assert analytics.trade_sharpe_ratio is not None
    assert analytics.downside_deviation == pytest.approx(
        (0.005 ** 2 / 3) ** 0.5
    )
    assert analytics.payoff_ratio == pytest.approx(
        1500.0 / 500.0
    )
    assert analytics.average_holding_seconds == 300.0
    assert analytics.maximum_holding_seconds == 300.0


def test_service_creates_month_code_hour_and_reason_breakdowns() -> None:
    analytics = (
        AdvancedPerformanceAnalyticsService()
        .create(report())
    )

    assert [item.key for item in analytics.monthly] == [
        "2026-07",
        "2026-08",
    ]
    assert [item.key for item in analytics.by_code] == [
        "6758",
        "7203",
    ]
    assert [item.key for item in analytics.by_entry_hour] == [
        "00:00",
        "01:00",
    ]
    assert [
        item.key
        for item in analytics.by_exit_reason
    ] == [
        "stop_loss",
        "take_profit",
        "unknown",
    ]

    code_7203 = next(
        item
        for item in analytics.by_code
        if item.key == "7203"
    )
    assert code_7203.trade_count == 2
    assert code_7203.win_rate == pytest.approx(0.5)
    assert code_7203.profit_factor == pytest.approx(2.0)
    assert code_7203.net_profit_loss == 500.0


def test_service_handles_empty_report() -> None:
    analytics = (
        AdvancedPerformanceAnalyticsService()
        .create(
            BacktestTradeReport(
                trades=(),
                unmatched_buy_quantity=0,
                unmatched_sell_quantity=0,
            )
        )
    )

    assert analytics.trade_count == 0
    assert analytics.trade_sharpe_ratio is None
    assert analytics.monthly == ()
