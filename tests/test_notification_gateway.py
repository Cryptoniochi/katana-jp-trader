"""NotificationGatewayのテスト。"""

from datetime import datetime, timezone

from app.notifications.notification_gateway import (
    NotificationGateway,
)
from app.notifications.notification_gateway_models import (
    NotificationGatewayRequest,
)
from app.notifications.notification_models import (
    NotificationChannelResult,
    NotificationDeliveryDecision,
    NotificationDeliveryResult,
    NotificationSeverity,
)
from app.notifications.notification_rule_models import (
    NotificationRoutingResult,
    NotificationRuleDecision,
    NotificationSuppressionReason,
    RuleBasedNotificationResult,
)
from app.notifications.notification_template import (
    NotificationTemplateName,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeSender:
    def __init__(
        self,
        *,
        suppress: bool = False,
    ) -> None:
        self.suppress = suppress
        self.notifications = []
        self.continue_on_error_values = []

    def deliver(
        self,
        notification,
        *,
        continue_on_error=True,
    ):
        self.notifications.append(notification)
        self.continue_on_error_values.append(
            continue_on_error
        )

        routing = NotificationRoutingResult(
            notification=notification,
            decision=(
                NotificationRuleDecision.SUPPRESS
                if self.suppress
                else NotificationRuleDecision.ROUTE
            ),
            channel_names=(
                ()
                if self.suppress
                else ("discord",)
            ),
            reasons=(
                (
                    NotificationSuppressionReason.NO_CHANNEL,
                )
                if self.suppress
                else ()
            ),
            evaluated_at=NOW,
        )

        if self.suppress:
            return RuleBasedNotificationResult(
                routing=routing,
                delivery=None,
            )

        delivery = NotificationDeliveryResult(
            notification=notification,
            decision=NotificationDeliveryDecision.COMPLETED,
            channels=(
                NotificationChannelResult(
                    channel_name="discord",
                    delivered=True,
                ),
            ),
        )

        return RuleBasedNotificationResult(
            routing=routing,
            delivery=delivery,
        )


class CollectingObserver:
    def __init__(self) -> None:
        self.results = []

    def record(self, result) -> None:
        self.results.append(result)


def request(
    *,
    severity=None,
) -> NotificationGatewayRequest:
    return NotificationGatewayRequest(
        notification_id="notice-1",
        template_name=NotificationTemplateName.SYSTEM_HEALTH,
        created_at=NOW,
        source="system-health",
        context={
            "status": "critical",
            "message": "broker unavailable",
        },
        severity=severity,
        metadata={
            "correlation_id": "health-1",
        },
    )


def test_gateway_renders_and_delivers_notification() -> None:
    sender = FakeSender()
    observer = CollectingObserver()
    gateway = NotificationGateway(
        sender=sender,
        observers=(observer,),
    )

    result = gateway.send(request())

    notification = sender.notifications[0]

    assert notification.title == "System Health: critical"
    assert notification.body == "broker unavailable"
    assert notification.severity is (
        NotificationSeverity.WARNING
    )
    assert notification.metadata == {
        "template_name": "system_health",
        "correlation_id": "health-1",
    }
    assert result.delivered_count == 1
    assert result.failed_count == 0
    assert result.was_suppressed is False
    assert len(observer.results) == 1


def test_request_severity_overrides_template_default() -> None:
    sender = FakeSender()
    gateway = NotificationGateway(sender=sender)

    result = gateway.send(
        request(
            severity=NotificationSeverity.CRITICAL
        ),
        continue_on_error=False,
    )

    assert result.notification.severity is (
        NotificationSeverity.CRITICAL
    )
    assert sender.continue_on_error_values == [False]


def test_suppressed_result_does_not_call_observer() -> None:
    sender = FakeSender(suppress=True)
    observer = CollectingObserver()
    gateway = NotificationGateway(
        sender=sender,
        observers=(observer,),
    )

    result = gateway.send(request())

    assert result.was_suppressed
    assert result.delivered_count == 0
    assert observer.results == []
