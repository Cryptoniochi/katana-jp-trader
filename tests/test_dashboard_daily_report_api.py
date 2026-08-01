"""Dashboard Daily Report APIのテスト。"""

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


class FakeDailyReportReader:
    def read_latest(self):
        return {
            "available": True,
            "report_date": "2026-08-03",
            "status": "complete",
            "summary": {
                "trade_count": 3,
                "net_profit_loss": 1200.0,
            },
            "strategy_breakdown": [],
            "symbol_breakdown": [],
            "error_count": 0,
            "recovery_count": 1,
            "notes": [],
            "message": None,
        }

    def read_for_date(self, report_date):
        payload = self.read_latest()
        payload["report_date"] = (
            report_date.isoformat()
        )
        return payload


def test_daily_report_api_returns_latest() -> None:
    app = create_dashboard_app(
        service=FakeDashboardService(),
        daily_report_reader=(
            FakeDailyReportReader()
        ),
    )

    response = TestClient(app).get(
        "/api/dashboard/daily-report"
    )

    assert response.status_code == 200
    assert response.json()["report_date"] == (
        "2026-08-03"
    )
    assert response.json()["summary"][
        "net_profit_loss"
    ] == 1200.0


def test_daily_report_api_accepts_date() -> None:
    app = create_dashboard_app(
        service=FakeDashboardService(),
        daily_report_reader=(
            FakeDailyReportReader()
        ),
    )

    response = TestClient(app).get(
        "/api/dashboard/daily-report"
        "?report_date=2026-08-01"
    )

    assert response.status_code == 200
    assert response.json()["report_date"] == (
        "2026-08-01"
    )


def test_daily_report_api_rejects_invalid_date() -> None:
    app = create_dashboard_app(
        service=FakeDashboardService(),
        daily_report_reader=(
            FakeDailyReportReader()
        ),
    )

    response = TestClient(app).get(
        "/api/dashboard/daily-report"
        "?report_date=08-01-2026"
    )

    assert response.status_code == 422
