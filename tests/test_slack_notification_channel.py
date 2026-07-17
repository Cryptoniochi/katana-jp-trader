"""SlackNotificationChannelのテスト。"""

from datetime import datetime, timezone

from app.notifications.notification_models import (
    NotificationMessage,
    NotificationSeverity,
)
from app.notifications.slack_notification_channel import (
    SlackNotificationChannel,
)
from app.notifications.slack_notification_models import (
    SlackNotificationSettings,
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
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


class FakeWebhookClient:
    def __init__(self) -> None:
        self.requests = []
        self.raise_on_failure_values = []

    def send(
        self,
        request,
        *,
        raise_on_failure: bool = True,
    ) -> WebhookDeliveryResult:
        self.requests.append(request)
        self.raise_on_failure_values.append(
            raise_on_failure
        )

        return WebhookDeliveryResult(
            url=request.url,
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
                body="ok",
            ),
        )


def message(
    *,
    severity: NotificationSeverity,
    title: str = "System Health",
    body: str = "All systems operational",
) -> NotificationMessage:
    return NotificationMessage(
        notification_id="notice-1",
        title=title,
        body=body,
        severity=severity,
        created_at=NOW,
        source="system-health",
        metadata={
            "event_type": "error_occurred",
            "code": "7203",
            "correlation_id": "health-1",
            "current_status": "warning",
        },
    )


def create_channel():
    client = FakeWebhookClient()
    channel = SlackNotificationChannel(
        settings=SlackNotificationSettings(
            webhook_url=(
                "https://hooks.slack.test/services/1"
            ),
            username="KATANA",
            icon_emoji=":crossed_swords:",
            channel="#alerts",
            mention="<!channel>",
        ),
        webhook_client=client,
    )
    return channel, client


def test_send_builds_slack_block_kit_payload() -> None:
    channel, client = create_channel()

    channel.send(
        message(
            severity=NotificationSeverity.CRITICAL
        )
    )

    request = client.requests[0]
    payload = request.payload

    assert channel.channel_name == "slack"
    assert request.url == (
        "https://hooks.slack.test/services/1"
    )
    assert payload["username"] == "KATANA"
    assert payload["icon_emoji"] == ":crossed_swords:"
    assert payload["channel"] == "#alerts"
    assert payload["blocks"][0]["text"]["text"] == (
        "<!channel>"
    )
    assert payload["blocks"][1]["type"] == "header"
    assert "🚨" in payload["blocks"][1]["text"]["text"]
    assert client.raise_on_failure_values == [True]


def test_each_severity_uses_expected_symbol() -> None:
    expected = {
        NotificationSeverity.INFO: "ℹ️",
        NotificationSeverity.WARNING: "⚠️",
        NotificationSeverity.ERROR: "❌",
        NotificationSeverity.CRITICAL: "🚨",
    }

    for severity, symbol in expected.items():
        channel, client = create_channel()
        channel.send(message(severity=severity))

        header = (
            client.requests[0]
            .payload["blocks"][1]["text"]["text"]
        )

        assert symbol in header


def test_metadata_is_added_as_fields() -> None:
    channel, client = create_channel()

    channel.send(
        message(
            severity=NotificationSeverity.ERROR
        )
    )

    fields = (
        client.requests[0]
        .payload["blocks"][3]["fields"]
    )
    texts = [
        item["text"]
        for item in fields
    ]

    assert any("ERROR" in text for text in texts)
    assert any("system-health" in text for text in texts)
    assert any("error_occurred" in text for text in texts)
    assert any("7203" in text for text in texts)
    assert any("health-1" in text for text in texts)
    assert any("warning" in text for text in texts)


def test_long_title_and_body_are_truncated() -> None:
    channel, client = create_channel()

    channel.send(
        message(
            severity=NotificationSeverity.INFO,
            title="T" * 200,
            body="B" * 4000,
        )
    )

    blocks = client.requests[0].payload["blocks"]
    header = blocks[1]["text"]["text"]
    body = blocks[2]["text"]["text"]

    assert len(header) == 150
    assert len(body) == 3000
    assert header.endswith("…")
    assert body.endswith("…")


def test_mrkdwn_special_characters_are_escaped() -> None:
    client = FakeWebhookClient()
    channel = SlackNotificationChannel(
        settings=SlackNotificationSettings(
            webhook_url=(
                "https://hooks.slack.test/services/1"
            ),
        ),
        webhook_client=client,
    )
    custom = NotificationMessage(
        notification_id="notice-2",
        title="Test",
        body="Body",
        severity=NotificationSeverity.INFO,
        created_at=NOW,
        source="<broker&api>",
        metadata={},
    )

    channel.send(custom)

    fields = (
        client.requests[0]
        .payload["blocks"][2]["fields"]
    )

    assert "&lt;broker&amp;api&gt;" in (
        fields[1]["text"]
    )
