"""SystemHealthEventPublisherのテスト。"""

from datetime import datetime, timezone

from app.events.domain_event_bus import DomainEventBus
from app.events.domain_events import DomainEventType
from app.monitoring.runtime_metrics import (
    RuntimeMetricName,
    RuntimeMetricsSnapshot,
)
from app.monitoring.system_health_event_publisher import (
    SystemHealthEventPublisher,
)
from app.monitoring.system_health_models import (
    SystemHealthReport,
    SystemHealthStatus,
)
from app.monitoring.system_health_transition import (
    SystemHealthTransition,
    SystemHealthTransitionType,
)
from app.monitoring.update_health_service import (
    UpdateHealthReport,
    UpdateHealthStatus,
)


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def transition(
    status: SystemHealthStatus,
) -> SystemHealthTransition:
    reasons = () if status is SystemHealthStatus.HEALTHY else (
        "runtime issue",
    )
    report = SystemHealthReport(
        status=status,
        checked_at=NOW,
        update_health=UpdateHealthReport(
            status=UpdateHealthStatus.HEALTHY,
            checked_at=NOW,
            reason="healthy",
            latest_run=None,
            latest_success=None,
            consecutive_failure_count=0,
            seconds_since_latest_run=None,
            seconds_since_latest_success=None,
        ),
        runtime_metrics=RuntimeMetricsSnapshot(
            generated_at=NOW,
            counts={
                RuntimeMetricName.DOMAIN_EVENT_COUNT: 10,
                RuntimeMetricName.ERROR_OCCURRED_COUNT: 2,
            },
        ),
        reasons=reasons,
    )

    return SystemHealthTransition(
        transition_type=(
            SystemHealthTransitionType.DEGRADED
        ),
        detected_at=NOW,
        previous_status=SystemHealthStatus.HEALTHY,
        current_status=status,
        previous_report=None,
        current_report=report,
        check_number=2,
    )


def test_publishes_health_change_as_domain_event() -> None:
    bus = DomainEventBus()
    received = []

    bus.subscribe(
        DomainEventType.ERROR_OCCURRED,
        received.append,
    )

    publisher = SystemHealthEventPublisher(
        event_bus=bus,
        event_id_provider=lambda: "health-event-1",
    )

    result = publisher.publish(
        transition(SystemHealthStatus.CRITICAL)
    )

    assert result.is_successful
    assert len(received) == 1
    event = received[0]
    assert event.event_id == "health-event-1"
    assert event.payload["severity"] == "critical"
    assert event.payload["current_status"] == "critical"
    assert event.payload["check_number"] == 2


def test_warning_maps_to_warning_severity() -> None:
    bus = DomainEventBus()
    received = []
    bus.subscribe(
        DomainEventType.ERROR_OCCURRED,
        received.append,
    )
    publisher = SystemHealthEventPublisher(
        event_bus=bus,
        event_id_provider=lambda: "health-event-2",
    )

    publisher.publish(
        transition(SystemHealthStatus.WARNING)
    )

    assert received[0].payload["severity"] == "warning"


def test_publisher_integrates_with_bus_history() -> None:
    bus = DomainEventBus(history_limit=10)
    publisher = SystemHealthEventPublisher(
        event_bus=bus,
        event_id_provider=lambda: "health-event-3",
    )

    publisher.publish(
        transition(SystemHealthStatus.DEGRADED)
    )

    history = bus.history(
        event_type=DomainEventType.ERROR_OCCURRED
    )

    assert len(history) == 1
    assert history[0].correlation_id == "system-health-2"
