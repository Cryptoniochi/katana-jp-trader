"""Daily Report UI接続のAPI回帰テスト。"""

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
            "source_path": "reports/daily/2026-08-01.json",
            "report_date": "2026-08-01",
            "generated_at": NOW.isoformat(),
            "status": "complete",
            "summary": {
                "trade_count": 2,
                "net_profit_loss": 1500.0,
                "win_rate": 0.5,
                "profit_factor": 2.0,
                "maximum_drawdown": -500.0,
            },
            "strategy_breakdown": [
                {
                    "key": "orb",
                    "label": "ORB",
                    "trade_count": 2,
                    "net_profit_loss": 1500.0,
                    "win_rate": 0.5,
                    "profit_factor": 2.0,
                }
            ],
            "symbol_breakdown": [],
            "error_count": 0,
            "recovery_count": 1,
            "notes": [],
            "message": None,
        }

    def read_for_date(self, report_date):
        return self.read_latest()


def test_daily_report_api_payload_supports_ui() -> None:
    app = create_dashboard_app(
        service=FakeDashboardService(),
        daily_report_reader=FakeDailyReportReader(),
    )

    response = TestClient(app).get(
        "/api/dashboard/daily-report"
    )

    payload = response.json()

    assert response.status_code == 200
    assert payload["available"]
    assert payload["summary"]["net_profit_loss"] == 1500.0
    assert payload["strategy_breakdown"][0]["label"] == "ORB"
    assert payload["recovery_count"] == 1
