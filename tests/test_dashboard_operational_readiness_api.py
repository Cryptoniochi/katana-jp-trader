"""Operational Readiness APIのテスト。"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.dashboard.dashboard_web_app import (
    create_dashboard_app,
)
from app.dashboard.dashboard_web_models import (
    DashboardWebPayload,
)
from app.runtime.operational_readiness_models import (
    OperationalReadinessPayload,
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


class FakeReadinessService:
    def evaluate(self):
        return OperationalReadinessPayload(
            generated_at=NOW,
            overall_state="ready",
            ready_for_paper_trading=True,
            checks=(),
        )


def test_readiness_api_is_exposed() -> None:
    app = create_dashboard_app(
        service=FakeDashboardService(),
        readiness_service=FakeReadinessService(),
    )
    response = TestClient(app).get(
        "/api/dashboard/operational-readiness"
    )

    assert response.status_code == 200
    assert response.json()["overall_state"] == "ready"
