"""Dashboard performance APIのテスト。"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.analytics.strategy_performance_models import (
    StrategyPerformance,
    StrategyPerformancePayload,
)
from app.dashboard.dashboard_web_app import (
    create_dashboard_app,
)
from app.dashboard.dashboard_web_models import (
    DashboardWebPayload,
)


NOW = datetime(
    2026,
    8,
    3,
    tzinfo=timezone.utc,
)


class FakeDashboardService:
    def create_payload(self):
        return DashboardWebPayload(
            generated_at=NOW,
            snapshot={
                "partial": False,
                "portfolio": None,
            },
            daily_history=(),
            cumulative_profit_loss=0.0,
        )


class FakePerformanceService:
    def analyze(self):
        return StrategyPerformancePayload(
            generated_at=NOW,
            period_start=None,
            period_end=None,
            rankings=(
                StrategyPerformance(
                    strategy_name="ORB",
                    trade_count=1,
                    win_count=1,
                    loss_count=0,
                    breakeven_count=0,
                    win_rate=1.0,
                    gross_profit=1000.0,
                    gross_loss=0.0,
                    net_profit_loss=1000.0,
                    profit_factor=float("inf"),
                    average_profit_loss=1000.0,
                    average_win=1000.0,
                    average_loss=None,
                    average_return_rate=0.01,
                    average_win_rate=0.01,
                    average_loss_rate=None,
                    expectancy=1000.0,
                    average_holding_minutes=30.0,
                    maximum_drawdown=0.0,
                    maximum_drawdown_rate=None,
                    average_mfe_rate=0.02,
                    average_mae_rate=-0.005,
                    score=60.0,
                ),
            ),
        )


def test_performance_api_is_exposed() -> None:
    app = create_dashboard_app(
        service=FakeDashboardService(),
        performance_service=FakePerformanceService(),
    )

    response = TestClient(app).get(
        "/api/dashboard/performance"
    )

    assert response.status_code == 200
    assert response.json()["rankings"][0][
        "strategy_name"
    ] == "ORB"
