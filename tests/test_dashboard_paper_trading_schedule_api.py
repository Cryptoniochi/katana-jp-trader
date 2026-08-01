"""Paper Trading Schedule APIのテスト。"""

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


class FakeScheduleReader:
    def read(self):
        return {
            "available": True,
            "state": "disabled",
            "enabled": False,
            "settings": {
                "start_at": "08:45",
                "stop_at": "15:35",
            },
        }


def test_schedule_api_is_exposed() -> None:
    app = create_dashboard_app(
        service=FakeDashboardService(),
        paper_schedule_reader=FakeScheduleReader(),
    )
    response = TestClient(app).get(
        "/api/dashboard/paper-trading-schedule"
    )

    assert response.status_code == 200
    assert response.json()["state"] == "disabled"
