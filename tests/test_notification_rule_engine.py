"""NotificationRuleEngineのテスト。"""

from datetime import datetime, timedelta, timezone

from app.notifications.notification_models import (
    NotificationMessage,
    NotificationSeverity,
)
from app.notifications.notification_rule_engine import (
    NotificationRuleEngine,
)
from app.notifications.notification_rule_models import (
    NotificationRuleDecision,
    NotificationRulePolicy,
    NotificationSuppressionReason,
)


BASE_TIME = datetime(
    2026,
    7,
    17,
    12,
    0,
    tzinfo=timezone.utc,
)


def message(
    *,
    notification_id: str = "notice-1",
    severity: NotificationSeverity = (
        NotificationSeverity.WARNING
    ),
    body: str = "test body",
) -> NotificationMessage:
    return NotificationMessage(
        notification_id=notification_id,
        title="Test",
        body=body,
        severity=severity,
        created_at=BASE_TIME,
        source="test",
    )


class Clock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


def test_routes_by_severity_and_available_channels() -> None:
    engine = NotificationRuleEngine(
        now_provider=lambda: BASE_TIME
    )

    result = engine.evaluate(
        message(
            severity=NotificationSeverity.WARNING
        ),
        available_channel_names=(
            "discord",
            "slack",
            "file",
        ),
    )

    assert result.decision is NotificationRuleDecision.ROUTE
    assert result.channel_names == (
        "discord",
        "slack",
    )


def test_suppresses_info_during_quiet_hours() -> None:
    quiet_time = BASE_TIME.replace(hour=23)
    engine = NotificationRuleEngine(
        now_provider=lambda: quiet_time
    )

    result = engine.evaluate(
        message(
            severity=NotificationSeverity.INFO
        ),
        available_channel_names=("file",),
    )

    assert not result.should_deliver
    assert NotificationSuppressionReason.QUIET_HOURS in (
        result.reasons
    )


def test_critical_is_not_suppressed_by_default_quiet_rule() -> None:
    quiet_time = BASE_TIME.replace(hour=23)
    engine = NotificationRuleEngine(
        now_provider=lambda: quiet_time
    )

    result = engine.evaluate(
        message(
            severity=NotificationSeverity.CRITICAL
        ),
        available_channel_names=("discord", "slack"),
    )

    assert result.should_deliver


def test_duplicate_content_is_suppressed_within_cooldown() -> None:
    clock = Clock(BASE_TIME)
    engine = NotificationRuleEngine(
        policy=NotificationRulePolicy(
            duplicate_cooldown_seconds=60,
        ),
        now_provider=clock,
    )

    first = engine.evaluate(
        message(notification_id="notice-1"),
        available_channel_names=("discord", "slack"),
    )
    clock.current += timedelta(seconds=30)
    second = engine.evaluate(
        message(notification_id="notice-2"),
        available_channel_names=("discord", "slack"),
    )

    assert first.should_deliver
    assert not second.should_deliver
    assert (
        NotificationSuppressionReason.DUPLICATE_COOLDOWN
        in second.reasons
    )


def test_duplicate_is_allowed_after_cooldown() -> None:
    clock = Clock(BASE_TIME)
    engine = NotificationRuleEngine(
        policy=NotificationRulePolicy(
            duplicate_cooldown_seconds=60,
        ),
        now_provider=clock,
    )

    engine.evaluate(
        message(),
        available_channel_names=("discord", "slack"),
    )
    clock.current += timedelta(seconds=60)

    result = engine.evaluate(
        message(notification_id="notice-2"),
        available_channel_names=("discord", "slack"),
    )

    assert result.should_deliver


def test_rate_limit_suppresses_non_critical_notification() -> None:
    clock = Clock(BASE_TIME)
    engine = NotificationRuleEngine(
        policy=NotificationRulePolicy(
            duplicate_cooldown_seconds=0,
            maximum_notifications_per_window=2,
            rate_window_seconds=60,
        ),
        now_provider=clock,
    )

    for index in range(2):
        result = engine.evaluate(
            message(body=f"body-{index}"),
            available_channel_names=("discord", "slack"),
        )
        assert result.should_deliver

    limited = engine.evaluate(
        message(body="body-3"),
        available_channel_names=("discord", "slack"),
    )

    assert not limited.should_deliver
    assert NotificationSuppressionReason.RATE_LIMIT in (
        limited.reasons
    )


def test_critical_bypasses_rate_limit() -> None:
    engine = NotificationRuleEngine(
        policy=NotificationRulePolicy(
            duplicate_cooldown_seconds=0,
            maximum_notifications_per_window=1,
        ),
        now_provider=lambda: BASE_TIME,
    )

    engine.evaluate(
        message(body="first"),
        available_channel_names=("discord", "slack"),
    )

    result = engine.evaluate(
        message(
            severity=NotificationSeverity.CRITICAL,
            body="critical",
        ),
        available_channel_names=("discord", "slack"),
    )

    assert result.should_deliver


def test_no_matching_channel_is_suppressed() -> None:
    engine = NotificationRuleEngine(
        now_provider=lambda: BASE_TIME
    )

    result = engine.evaluate(
        message(),
        available_channel_names=("file",),
    )

    assert not result.should_deliver
    assert NotificationSuppressionReason.NO_CHANNEL in (
        result.reasons
    )
