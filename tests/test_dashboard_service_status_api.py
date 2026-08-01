"""Dashboard Service Status APIのテスト。"""

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


class FakeStatusReader:
    def read(self):
        return {
            "available": True,
            "generated_at": NOW.isoformat(),
            "service_state": "healthy",
            "kabu_station_readiness": "ready",
            "components": [
                {
                    "name": "dashboard",
                    "state": "running",
                    "enabled": True,
                    "process_id": 3120,
                    "restart_count": 0,
                    "last_exit_code": None,
                    "started_at": None,
                    "updated_at": NOW.isoformat(),
                    "message": None,
                }
            ],
            "message": None,
        }


def test_service_status_api_is_exposed() -> None:
    app = create_dashboard_app(
        service=FakeDashboardService(),
        service_status_reader=FakeStatusReader(),
    )

    response = TestClient(app).get(
        "/api/dashboard/service-status"
    )

    assert response.status_code == 200
    assert response.json()["service_state"] == "healthy"
    assert response.json()["components"][0][
        "name"
    ] == "dashboard"
