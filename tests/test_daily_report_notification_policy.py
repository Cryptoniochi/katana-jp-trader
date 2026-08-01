"""Daily Report通知CLIのPolicy設定テスト。"""

from app.notifications.notification_models import (
    NotificationSeverity,
)
from app.notifications.notification_rule_models import (
    NotificationRulePolicy,
)


def test_daily_report_policy_can_disable_quiet_hours() -> None:
    policy = NotificationRulePolicy(
        info_channels=("discord", "line"),
        warning_channels=("discord", "line"),
        error_channels=("discord", "line"),
        critical_channels=("discord", "line"),
        quiet_hours_suppressed_severities=frozenset(),
        duplicate_cooldown_seconds=0,
    )

    assert (
        policy.quiet_hours_suppressed_severities
        == frozenset()
    )
    assert policy.channels_for(
        NotificationSeverity.INFO
    ) == (
        "discord",
        "line",
    )
