"""DiscordNotificationChannelのテスト。"""

from datetime import datetime, timezone

from app.notifications.discord_notification_channel import (
    DiscordNotificationChannel,
)
from app.notifications.discord_notification_models import (
    DiscordNotificationSettings,
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
                    status_code=204,
                    error_message=None,
                ),
            ),
            response=WebhookResponse(
                status_code=204
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
            "current_status": "critical",
        },
    )


def create_channel():
    client = FakeWebhookClient()
    channel = DiscordNotificationChannel(
        settings=DiscordNotificationSettings(
            webhook_url="https://discord.test/hook",
            username="KATANA",
            avatar_url=(
                "https://example.test/avatar.png"
            ),
            mention="@here",
        ),
        webhook_client=client,
    )
    return channel, client


def test_send_builds_discord_embed_payload() -> None:
    channel, client = create_channel()

    channel.send(
        message(
            severity=NotificationSeverity.CRITICAL
        )
    )

    request = client.requests[0]
    payload = request.payload
    embed = payload["embeds"][0]

    assert channel.channel_name == "discord"
    assert request.url == "https://discord.test/hook"
    assert payload["username"] == "KATANA"
    assert payload["avatar_url"] == (
        "https://example.test/avatar.png"
    )
    assert payload["content"] == "@here"
    assert embed["title"] == "System Health"
    assert embed["description"] == (
        "All systems operational"
    )
    assert embed["color"] == 0x9B59B6
    assert embed["timestamp"] == NOW.isoformat()
    assert client.raise_on_failure_values == [True]


def test_each_severity_uses_expected_color() -> None:
    expected = {
        NotificationSeverity.INFO: 0x3498DB,
        NotificationSeverity.WARNING: 0xF1C40F,
        NotificationSeverity.ERROR: 0xE74C3C,
        NotificationSeverity.CRITICAL: 0x9B59B6,
    }

    for severity, color in expected.items():
        channel, client = create_channel()
        channel.send(message(severity=severity))

        assert (
            client.requests[0]
            .payload["embeds"][0]["color"]
            == color
        )


def test_metadata_is_added_as_embed_fields() -> None:
    channel, client = create_channel()

    channel.send(
        message(
            severity=NotificationSeverity.ERROR
        )
    )

    fields = (
        client.requests[0]
        .payload["embeds"][0]["fields"]
    )
    field_map = {
        item["name"]: item["value"]
        for item in fields
    }

    assert field_map["Severity"] == "ERROR"
    assert field_map["Source"] == "system-health"
    assert field_map["event_type"] == (
        "error_occurred"
    )
    assert field_map["code"] == "7203"
    assert field_map["correlation_id"] == "health-1"
    assert field_map["current_status"] == "critical"


def test_long_title_and_body_are_truncated() -> None:
    channel, client = create_channel()

    channel.send(
        message(
            severity=NotificationSeverity.INFO,
            title="T" * 300,
            body="B" * 5000,
        )
    )

    embed = (
        client.requests[0]
        .payload["embeds"][0]
    )

    assert len(embed["title"]) == 256
    assert len(embed["description"]) == 4096
    assert embed["title"].endswith("…")
    assert embed["description"].endswith("…")
