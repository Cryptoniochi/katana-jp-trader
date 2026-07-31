"""Dashboard strategy APIのテスト。"""

from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from app.dashboard.dashboard_strategy_service import (
    DashboardStrategyPayload,
    DashboardStrategyRow,
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


class FakeStrategyService:
    def create_payload(self):
        return DashboardStrategyPayload(
            generated_at=NOW,
            trading_date=date(2026, 8, 3),
            strategies=(
                DashboardStrategyRow(
                    strategy_name="ORB",
                    signal_count=1,
                    execution_count=1,
                    completed_trade_count=0,
                    win_count=0,
                    loss_count=0,
                    net_profit_loss=0.0,
                    win_rate=None,
                    profit_factor=None,
                ),
            ),
            recent_trades=(),
        )


def test_strategy_api_is_exposed() -> None:
    app = create_dashboard_app(
        service=FakeDashboardService(),
        strategy_service=FakeStrategyService(),
    )
    response = TestClient(app).get(
        "/api/dashboard/strategies"
    )

    assert response.status_code == 200
    assert response.json()["strategies"][0][
        "strategy_name"
    ] == "ORB"



def test_strategy_api_contains_completed_trade_key() -> None:
    app = create_dashboard_app(
        service=FakeDashboardService(),
        strategy_service=FakeStrategyService(),
    )
    payload = TestClient(app).get(
        "/api/dashboard/strategies"
    ).json()

    assert "recent_completed_trades" in payload
