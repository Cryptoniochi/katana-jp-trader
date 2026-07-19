"""外部通知テストCLIのテスト。"""

from datetime import datetime, timezone
from io import StringIO

from app.notification_test import (
    create_test_policy,
    send_test_notification,
)
from app.notifications.notification_gateway import (
    NotificationGateway,
)
from app.notifications.notification_models import (
    NotificationChannelResult,
    NotificationDeliveryDecision,
    NotificationDeliveryResult,
)
from app.notifications.notification_rule_models import (
    NotificationRoutingResult,
    NotificationRuleDecision,
    RuleBasedNotificationResult,
)
from app.notifications.notification_composition import (
    NotificationCompositionBundle,
)
from app.settings import NotificationSettings


NOW = datetime(
    2026,
    7,
    19,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeSender:
    def __init__(self) -> None:
        self.notifications = []

    def deliver(
        self,
        notification,
        *,
        continue_on_error=True,
    ):
        self.notifications.append(notification)

        routing = NotificationRoutingResult(
            notification=notification,
            decision=NotificationRuleDecision.ROUTE,
            channel_names=("discord", "line"),
            reasons=(),
            evaluated_at=NOW,
        )
        delivery = NotificationDeliveryResult(
            notification=notification,
            decision=NotificationDeliveryDecision.COMPLETED,
            channels=(
                NotificationChannelResult(
                    channel_name="discord",
                    delivered=True,
                ),
                NotificationChannelResult(
                    channel_name="line",
                    delivered=True,
                ),
            ),
        )

        return RuleBasedNotificationResult(
            routing=routing,
            delivery=delivery,
        )


class FakeRuleEngine:
    pass


class FakeChannel:
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def channel_name(self) -> str:
        return self._name

    def send(self, message) -> None:
        raise AssertionError(
            "FakeSender経由のため呼び出されません。"
        )


def test_test_policy_routes_every_severity_to_enabled_channels() -> None:
    policy = create_test_policy(
        ("discord", "line")
    )

    assert policy.info_channels == (
        "discord",
        "line",
    )
    assert policy.warning_channels == (
        "discord",
        "line",
    )
    assert policy.error_channels == (
        "discord",
        "line",
    )
    assert policy.critical_channels == (
        "discord",
        "line",
    )
    assert policy.duplicate_cooldown_seconds == 0


def test_send_test_notification_uses_gateway() -> None:
    sender = FakeSender()
    gateway = NotificationGateway(
        sender=sender
    )
    bundle = NotificationCompositionBundle(
        settings=NotificationSettings(),
        gateway=gateway,
        sender=sender,
        rule_engine=FakeRuleEngine(),
        channels=(
            FakeChannel("discord"),
            FakeChannel("line"),
        ),
    )

    result = send_test_notification(
        bundle=bundle,
        title="Notification Test",
        message="Connection succeeded",
        created_at=NOW,
    )

    notification = sender.notifications[0]

    assert notification.title == "Notification Test"
    assert notification.body == "Connection succeeded"
    assert notification.source == (
        "notification-test-cli"
    )
    assert notification.metadata[
        "event_type"
    ] == "connection_test"
    assert result.delivered_count == 2
