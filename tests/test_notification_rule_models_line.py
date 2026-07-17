"""LINEを含む通知ルール既定値のテスト。"""

from app.notifications.notification_models import (
    NotificationSeverity,
)
from app.notifications.notification_rule_models import (
    NotificationRulePolicy,
)


def test_default_error_and_critical_routes_include_line() -> None:
    policy = NotificationRulePolicy()

    assert policy.channels_for(
        NotificationSeverity.ERROR
    ) == (
        "discord",
        "slack",
        "line",
    )
    assert policy.channels_for(
        NotificationSeverity.CRITICAL
    ) == (
        "discord",
        "slack",
        "line",
    )


def test_warning_does_not_include_line_by_default() -> None:
    policy = NotificationRulePolicy()

    assert policy.channels_for(
        NotificationSeverity.WARNING
    ) == (
        "discord",
        "slack",
    )
