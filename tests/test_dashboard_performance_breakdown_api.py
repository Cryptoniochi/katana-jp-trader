"""Dashboard Performance Breakdown APIのテスト。"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.analytics.performance_breakdown_models import (
    PerformanceBreakdownPayload,
    PerformanceBreakdownRow,
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


class FakeBreakdownService:
    def analyze(self):
        row = PerformanceBreakdownRow(
            key="0",
            label="Monday",
            trade_count=1,
            win_count=1,
            loss_count=0,
            win_rate=1.0,
            net_profit_loss=1000.0,
            gross_profit=1000.0,
            gross_loss=0.0,
            profit_factor=float("inf"),
            average_profit_loss=1000.0,
            average_return_rate=0.01,
        )
        return PerformanceBreakdownPayload(
            generated_at=NOW,
            weekday=(row,),
            entry_hour=(),
            symbol=(),
            exit_reason=(),
        )


def test_breakdown_api_is_exposed() -> None:
    app = create_dashboard_app(
        service=FakeDashboardService(),
        breakdown_service=FakeBreakdownService(),
    )
    response = TestClient(app).get(
        "/api/dashboard/performance-breakdown"
    )

    assert response.status_code == 200
    assert response.json()["weekday"][0][
        "label"
    ] == "Monday"
