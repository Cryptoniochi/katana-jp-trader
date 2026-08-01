"""DailyReportNotificationServiceのテスト。"""

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.notifications.daily_report_notification_service import (
    DailyReportNotificationService,
)


NOW = datetime(
    2026,
    8,
    3,
    15,
    40,
    tzinfo=timezone.utc,
)


class FakeReader:
    def read_latest(self):
        return self.read_for_date(
            date(2026, 8, 3)
        )

    def read_for_date(self, report_date):
        return {
            "available": True,
            "report_date": report_date.isoformat(),
            "status": "complete",
            "summary": {
                "trade_count": 1,
                "net_profit_loss": 500.0,
                "win_rate": 1.0,
                "profit_factor": 500.0,
                "maximum_drawdown": 0.0,
            },
            "strategy_breakdown": [],
            "symbol_breakdown": [],
            "error_count": 0,
            "recovery_count": 0,
            "notes": [],
        }


class FakeGateway:
    def __init__(self):
        self.requests = []

    def send(
        self,
        request,
        *,
        continue_on_error=True,
    ):
        self.requests.append(
            (
                request,
                continue_on_error,
            )
        )
        return SimpleNamespace(
            delivered_count=2,
            failed_count=0,
            was_suppressed=False,
        )


def test_service_sends_generic_gateway_request() -> None:
    gateway = FakeGateway()
    result = DailyReportNotificationService(
        reader=FakeReader(),
        gateway=gateway,
    ).send_latest(
        created_at=NOW,
    )

    request, continue_on_error = (
        gateway.requests[0]
    )

    assert request.source == "daily_report"
    assert request.context["title"].startswith(
        "Project KATANA Daily Report"
    )
    assert "+500円" in request.context["message"]
    assert request.metadata["event_type"] == (
        "daily_report"
    )
    assert continue_on_error
    assert result.delivered_count == 2


def test_service_sends_requested_date() -> None:
    gateway = FakeGateway()
    DailyReportNotificationService(
        reader=FakeReader(),
        gateway=gateway,
    ).send_for_date(
        date(2026, 8, 1),
        created_at=NOW,
        continue_on_error=False,
    )

    request, continue_on_error = (
        gateway.requests[0]
    )

    assert request.metadata["report_date"] == (
        "2026-08-01"
    )
    assert not continue_on_error
