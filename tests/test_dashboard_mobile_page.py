"""Dashboard mobile pageのテスト。"""

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


def test_mobile_dashboard_page_is_available() -> None:
    client = TestClient(
        create_dashboard_app(
            service=FakeDashboardService(),
        )
    )

    response = client.get("/mobile")

    assert response.status_code == 200
    assert "Mobile Monitor" in response.text
    assert "mobile-strategy-list" in response.text
