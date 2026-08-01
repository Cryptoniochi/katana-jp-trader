"""Service Status routeの回帰テスト。"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.dashboard.dashboard_web_app import (
    create_dashboard_app,
)
from app.dashboard.dashboard_web_models import (
    DashboardWebPayload,
)


NOW = datetime(
    2026,
    8,
    1,
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


def test_service_status_route_exists_without_reader() -> None:
    response = TestClient(
        create_dashboard_app(
            service=FakeDashboardService(),
        )
    ).get(
        "/api/dashboard/service-status"
    )

    assert response.status_code == 200
    assert response.json()["service_state"] == (
        "not_configured"
    )
