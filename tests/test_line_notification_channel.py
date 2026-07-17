"""LineNotificationChannelのテスト。"""

from datetime import datetime, timezone

from app.notifications.line.line_models import (
    LineNotificationSettings,
)
from app.notifications.line.line_notification_channel import (
    LineNotificationChannel,
)
from app.notifications.line.line_result import (
    LineDeliveryResult,
)
from app.notifications.notification_models import (
    NotificationMessage,
    NotificationSeverity,
)
from app.notifications.webhook_models import (
    WebhookAttemptResult,
    WebhookDeliveryResult,
    WebhookResponse,
    WebhookRetryDecision,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeLineService:
    def __init__(self) -> None:
        self.requests = []
        self.raise_on_failure_values = []

    def deliver(
        self,
        request,
        *,
        raise_on_failure: bool = True,
    ) -> LineDeliveryResult:
        self.requests.append(request)
        self.raise_on_failure_values.append(
            raise_on_failure
        )

        return LineDeliveryResult(
            destination_id=request.destination_id,
            delivery=WebhookDeliveryResult(
                url=(
                    "https://api.line.me"
                    "/v2/bot/message/push"
                ),
                attempts=(
                    WebhookAttemptResult(
                        attempt_number=1,
                        decision=(
                            WebhookRetryDecision.SUCCEEDED
                        ),
                        status_code=200,
                        error_message=None,
                    ),
                ),
                response=WebhookResponse(
                    status_code=200,
                    body="{}",
                ),
            ),
        )


def message(
    *,
    severity: NotificationSeverity,
    title: str = "Fault Tolerance",
    body: str = "Recovery failed",
) -> NotificationMessage:
    return NotificationMessage(
        notification_id="notice-1",
        title=title,
        body=body,
        severity=severity,
        created_at=NOW,
        source="fault-tolerance",
        metadata={
            "decision": "safe_stop",
            "worker_name": "live-worker",
            "restart_count": 3,
        },
    )


def create_channel():
    service = FakeLineService()
    settings = LineNotificationSettings(
        channel_access_token="secret-token",
        destination_id="U1234567890",
    )
    channel = LineNotificationChannel(
        settings=settings,
        service=service,
    )
    return channel, service


def test_channel_sends_notification_as_line_text() -> None:
    channel, service = create_channel()

    channel.send(
        message(
            severity=NotificationSeverity.CRITICAL
        )
    )

    request = service.requests[0]
    text = request.messages[0].text

    assert channel.channel_name == "line"
    assert request.destination_id == "U1234567890"
    assert "🚨 [CRITICAL] Fault Tolerance" in text
    assert "Recovery failed" in text
    assert "decision=safe_stop" in text
    assert "worker_name=live-worker" in text
    assert "restart_count=3" in text
    assert "source=fault-tolerance" in text
    assert service.raise_on_failure_values == [True]


def test_channel_uses_expected_severity_symbols() -> None:
    expected = {
        NotificationSeverity.INFO: "ℹ️",
        NotificationSeverity.WARNING: "⚠️",
        NotificationSeverity.ERROR: "❌",
        NotificationSeverity.CRITICAL: "🚨",
    }

    for severity, symbol in expected.items():
        channel, service = create_channel()
        channel.send(message(severity=severity))

        assert service.requests[0].messages[0].text.startswith(
            symbol
        )


def test_channel_truncates_text_to_line_limit() -> None:
    channel, service = create_channel()

    channel.send(
        message(
            severity=NotificationSeverity.ERROR,
            title="T" * 100,
            body="B" * 6000,
        )
    )

    text = service.requests[0].messages[0].text

    assert len(text) == 5000
    assert text.endswith("…")
