"""MorningPreflightNotificationServiceのテスト。"""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.notifications.morning_preflight_notification_service import (
    MorningPreflightNotificationService,
)


NOW = datetime(
    2026,
    8,
    3,
    8,
    40,
    tzinfo=timezone.utc,
)


class FakeReport:
    def __init__(self, ready=True):
        self.ready = ready

    def to_dict(self):
        return {
            "overall_state": (
                "ready"
                if self.ready
                else "blocked"
            ),
            "ready_for_next_business_day": self.ready,
            "checks": [],
        }


class FakeValidator:
    def __init__(self, ready=True):
        self.ready = ready

    def evaluate(self):
        return FakeReport(self.ready)


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
        )


def test_service_sends_ready_notification() -> None:
    gateway = FakeGateway()
    result = MorningPreflightNotificationService(
        validator=FakeValidator(True),
        gateway=gateway,
    ).send(
        created_at=NOW,
    )

    request, continue_on_error = (
        gateway.requests[0]
    )

    assert request.source == "morning_preflight"
    assert request.metadata[
        "ready_for_next_business_day"
    ]
    assert continue_on_error
    assert result.delivered_count == 2


def test_service_sends_blocked_notification() -> None:
    gateway = FakeGateway()
    MorningPreflightNotificationService(
        validator=FakeValidator(False),
        gateway=gateway,
    ).send(
        created_at=NOW,
    )

    request, _ = gateway.requests[0]

    assert not request.metadata[
        "ready_for_next_business_day"
    ]
    assert "NOT READY" in request.context[
        "message"
    ]
