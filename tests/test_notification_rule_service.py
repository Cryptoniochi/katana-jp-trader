"""RuleBasedNotificationServiceのテスト。"""

from datetime import datetime, timezone

from app.notifications.notification_models import (
    NotificationMessage,
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


NOW = datetime(
    2026,
    7,
    17,
    12,
    0,
    tzinfo=timezone.utc,
)


class FakeChannel:
    def __init__(self, name: str) -> None:
        self._name = name
        self.messages = []

    @property
    def channel_name(self) -> str:
        return self._name

    def send(self, message) -> None:
        self.messages.append(message)


def notification(
    severity: NotificationSeverity,
) -> NotificationMessage:
    return NotificationMessage(
        notification_id="notice-1",
        title="Test",
        body="Body",
        severity=severity,
        created_at=NOW,
        source="test",
    )


def test_service_delivers_only_selected_channels() -> None:
    file_channel = FakeChannel("file")
    discord = FakeChannel("discord")
    slack = FakeChannel("slack")
    service = RuleBasedNotificationService(
        channels=(file_channel, discord, slack),
        rule_engine=NotificationRuleEngine(
            now_provider=lambda: NOW
        ),
    )

    result = service.deliver(
        notification(NotificationSeverity.WARNING)
    )

    assert result.routing.should_deliver
    assert result.delivery is not None
    assert file_channel.messages == []
    assert len(discord.messages) == 1
    assert len(slack.messages) == 1


def test_service_returns_suppression_without_delivery() -> None:
    file_channel = FakeChannel("file")
    service = RuleBasedNotificationService(
        channels=(file_channel,),
        rule_engine=NotificationRuleEngine(
            policy=NotificationRulePolicy(
                warning_channels=("discord",),
            ),
            now_provider=lambda: NOW,
        ),
    )

    result = service.deliver(
        notification(NotificationSeverity.WARNING)
    )

    assert not result.routing.should_deliver
    assert result.delivery is None
    assert file_channel.messages == []
