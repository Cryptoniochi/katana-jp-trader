"""Read-only FastAPI Dashboardのテスト。"""

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
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeService:
    def create_payload(self) -> DashboardWebPayload:
        return DashboardWebPayload(
            generated_at=NOW,
            snapshot={
                "complete": True,
                "partial": False,
                "portfolio": {
                    "positions": [],
                },
                "broker": {
                    "connected": True,
                    "name": "paper",
                    "message": None,
                },
            },
            daily_history=(),
            cumulative_profit_loss=0.0,
        )


def client() -> TestClient:
    return TestClient(
        create_dashboard_app(
            service=FakeService()
        )
    )


def test_dashboard_page_is_rendered() -> None:
    response = client().get("/")

    assert response.status_code == 200
    assert "Project KATANA" in response.text
    assert "Operations Dashboard" in response.text


def test_summary_api_is_read_only_json() -> None:
    response = client().get(
        "/api/dashboard/summary"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["generated_at"] == NOW.isoformat()
    assert payload["snapshot"]["complete"] is True


def test_equity_and_positions_api() -> None:
    test_client = client()

    equity = test_client.get(
        "/api/dashboard/equity"
    )
    positions = test_client.get(
        "/api/dashboard/positions"
    )

    assert equity.status_code == 200
    assert equity.json()["points"] == []
    assert positions.status_code == 200
    assert positions.json()["positions"] == []
