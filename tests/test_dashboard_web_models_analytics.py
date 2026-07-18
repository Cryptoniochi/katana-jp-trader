"""Dashboard Web分析モデルのテスト。"""

from datetime import date, datetime, timezone

import pytest

from app.dashboard.dashboard_web_models import (
    DashboardDailyPoint,
    DashboardWebPayload,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def point(
    *,
    day: int,
    profit: float,
    drawdown: float,
) -> DashboardDailyPoint:
    return DashboardDailyPoint(
        trading_date=date(2026, 7, day),
        net_profit_loss=profit,
        final_equity=1_000_000.0 + profit,
        return_rate=profit / 1_000_000.0,
        cumulative_profit_loss=profit,
        cumulative_return=profit / 1_000_000.0,
        drawdown=drawdown,
    )


def test_payload_calculates_daily_analytics() -> None:
    payload = DashboardWebPayload(
        generated_at=NOW,
        snapshot={},
        daily_history=(
            point(
                day=17,
                profit=10_000.0,
                drawdown=0.0,
            ),
            point(
                day=18,
                profit=-2_000.0,
                drawdown=0.01,
            ),
        ),
        cumulative_profit_loss=8_000.0,
    )

    value = payload.to_dict()

    assert payload.winning_day_count == 1
    assert payload.losing_day_count == 1
    assert payload.daily_win_rate == pytest.approx(0.5)
    assert payload.maximum_drawdown == pytest.approx(0.01)
    assert value["analytics"]["trading_day_count"] == 2
    assert value["analytics"]["daily_win_rate"] == pytest.approx(
        0.5
    )


def test_daily_point_rejects_negative_drawdown() -> None:
    with pytest.raises(ValueError, match="Drawdown"):
        DashboardDailyPoint(
            trading_date=date(2026, 7, 18),
            net_profit_loss=0.0,
            final_equity=1_000_000.0,
            return_rate=0.0,
            drawdown=-0.01,
        )
