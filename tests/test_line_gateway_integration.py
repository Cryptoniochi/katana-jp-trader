"""Notification GatewayからLINEまでの統合テスト。"""

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
from app.notifications.notification_gateway import (
    NotificationGateway,
)
from app.notifications.notification_gateway_models import (
    NotificationGatewayRequest,
)
from app.notifications.notification_models import (
    NotificationSeverity,
)
from app.notifications.notification_rule_engine import (
    NotificationRuleEngine,
)
from app.notifications.notification_rule_models import (
    NotificationRulePolicy,
)
from app.notifications.notification_rule_service import (
    RuleBasedNotificationService,
)
from app.notifications.notification_template import (
    NotificationTemplateName,
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
    12,
    0,
    tzinfo=timezone.utc,
)


class FakeLineService:
    def __init__(self) -> None:
        self.requests = []

    def deliver(
        self,
        request,
        *,
        raise_on_failure: bool = True,
    ) -> LineDeliveryResult:
        self.requests.append(request)

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


class CollectingChannel:
    def __init__(self, name: str) -> None:
        self._name = name
        self.messages = []

    @property
    def channel_name(self) -> str:
        return self._name

    def send(self, message) -> None:
        self.messages.append(message)


def test_gateway_routes_critical_to_discord_slack_and_line() -> None:
    discord = CollectingChannel("discord")
    slack = CollectingChannel("slack")
    line_service = FakeLineService()
    line = LineNotificationChannel(
        settings=LineNotificationSettings(
            channel_access_token="secret-token",
            destination_id="U1234567890",
        ),
        service=line_service,
    )
    sender = RuleBasedNotificationService(
        channels=(discord, slack, line),
        rule_engine=NotificationRuleEngine(
            policy=NotificationRulePolicy(
                duplicate_cooldown_seconds=0,
            ),
            now_provider=lambda: NOW,
        ),
    )
    gateway = NotificationGateway(
        sender=sender
    )

    result = gateway.send(
        NotificationGatewayRequest(
            notification_id="fault-1",
            template_name=(
                NotificationTemplateName.FAULT_TOLERANCE
            ),
            created_at=NOW,
            source="fault-tolerance",
            context={
                "decision": "safe_stop",
                "message": (
                    "Consecutive recovery failures"
                ),
            },
            severity=NotificationSeverity.CRITICAL,
            metadata={
                "worker_name": "live-worker",
                "consecutive_failure_count": 3,
            },
        )
    )

    assert result.delivered_count == 3
    assert result.failed_count == 0
    assert result.was_suppressed is False
    assert len(discord.messages) == 1
    assert len(slack.messages) == 1
    assert len(line_service.requests) == 1

    line_text = (
        line_service.requests[0]
        .messages[0]
        .text
    )

    assert "🚨 [CRITICAL]" in line_text
    assert "Fault Tolerance: safe_stop" in line_text
    assert "Consecutive recovery failures" in line_text
    assert "worker_name=live-worker" in line_text
    assert "consecutive_failure_count=3" in line_text


def test_gateway_does_not_route_warning_to_line_by_default() -> None:
    discord = CollectingChannel("discord")
    slack = CollectingChannel("slack")
    line_service = FakeLineService()
    line = LineNotificationChannel(
        settings=LineNotificationSettings(
            channel_access_token="secret-token",
            destination_id="U1234567890",
        ),
        service=line_service,
    )
    sender = RuleBasedNotificationService(
        channels=(discord, slack, line),
        rule_engine=NotificationRuleEngine(
            policy=NotificationRulePolicy(
                duplicate_cooldown_seconds=0,
            ),
            now_provider=lambda: NOW,
        ),
    )
    gateway = NotificationGateway(
        sender=sender
    )

    result = gateway.send(
        NotificationGatewayRequest(
            notification_id="health-1",
            template_name=(
                NotificationTemplateName.SYSTEM_HEALTH
            ),
            created_at=NOW,
            source="system-health",
            context={
                "status": "warning",
                "message": "Minor issue",
            },
            severity=NotificationSeverity.WARNING,
        )
    )

    assert result.delivered_count == 2
    assert len(discord.messages) == 1
    assert len(slack.messages) == 1
    assert line_service.requests == []
