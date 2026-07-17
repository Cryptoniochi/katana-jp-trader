"""NotificationMetricsAdapterのテスト。"""

from datetime import datetime, timezone

from app.monitoring.notification_metrics_adapter import (
    NotificationMetricsAdapter,
)
from app.monitoring.runtime_metrics import RuntimeMetricName
from app.monitoring.runtime_metrics_service import (
    RuntimeMetricsService,
)
from app.notifications.notification_models import (
    NotificationChannelResult,
    NotificationDeliveryDecision,
    NotificationDeliveryResult,
    NotificationMessage,
    NotificationSeverity,
)


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def notification() -> NotificationMessage:
    return NotificationMessage(
        notification_id="notice-1",
        title="Test",
        body="Body",
        severity=NotificationSeverity.INFO,
        created_at=NOW,
        source="test",
    )


def test_adapter_records_delivered_and_failed_channels() -> None:
    service = RuntimeMetricsService(
        now_provider=lambda: NOW
    )
    adapter = NotificationMetricsAdapter(
        service=service
    )
    result = NotificationDeliveryResult(
        notification=notification(),
        decision=(
            NotificationDeliveryDecision
            .COMPLETED_WITH_ERRORS
        ),
        channels=(
            NotificationChannelResult(
                channel_name="console",
                delivered=True,
            ),
            NotificationChannelResult(
                channel_name="file",
                delivered=False,
                error_message="write failed",
            ),
        ),
    )

    adapter.record(result)

    assert service.get(
        RuntimeMetricName.NOTIFICATION_DELIVERED_COUNT
    ) == 1
    assert service.get(
        RuntimeMetricName.NOTIFICATION_FAILED_COUNT
    ) == 1


def test_adapter_ignores_skipped_delivery() -> None:
    service = RuntimeMetricsService(
        now_provider=lambda: NOW
    )
    adapter = NotificationMetricsAdapter(
        service=service
    )
    result = NotificationDeliveryResult(
        notification=notification(),
        decision=NotificationDeliveryDecision.SKIPPED,
        channels=(),
    )

    adapter.record(result)

    snapshot = service.snapshot()

    assert snapshot.notification_attempt_count == 0
