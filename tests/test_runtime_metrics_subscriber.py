"""RuntimeMetricsSubscriberのテスト。"""

from datetime import datetime, timezone

from app.events.domain_event_bus import DomainEventBus
from app.events.domain_events import (
    DomainEvent,
    DomainEventType,
)
from app.monitoring.runtime_metrics import RuntimeMetricName
from app.monitoring.runtime_metrics_service import (
    RuntimeMetricsService,
)
from app.monitoring.runtime_metrics_subscriber import (
    RuntimeMetricsSubscriber,
)


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def create_event(
    event_id: str,
    event_type: DomainEventType,
) -> DomainEvent:
    return DomainEvent(
        event_id=event_id,
        event_type=event_type,
        occurred_at=NOW,
        source="test",
    )


def test_subscriber_counts_total_and_event_type() -> None:
    service = RuntimeMetricsService(
        now_provider=lambda: NOW
    )
    subscriber = RuntimeMetricsSubscriber(
        service=service
    )

    subscriber(
        create_event(
            "event-1",
            DomainEventType.ORDER_CREATED,
        )
    )
    subscriber(
        create_event(
            "event-2",
            DomainEventType.ORDER_UPDATED,
        )
    )

    assert service.get(
        RuntimeMetricName.DOMAIN_EVENT_COUNT
    ) == 2
    assert service.get(
        RuntimeMetricName.ORDER_CREATED_COUNT
    ) == 1
    assert service.get(
        RuntimeMetricName.ORDER_UPDATED_COUNT
    ) == 1


def test_subscriber_counts_error_event() -> None:
    service = RuntimeMetricsService(
        now_provider=lambda: NOW
    )
    subscriber = RuntimeMetricsSubscriber(
        service=service
    )

    subscriber(
        create_event(
            "event-1",
            DomainEventType.ERROR_OCCURRED,
        )
    )

    snapshot = service.snapshot()

    assert snapshot.domain_event_count == 1
    assert snapshot.error_count == 1


def test_subscriber_works_with_event_bus() -> None:
    service = RuntimeMetricsService(
        now_provider=lambda: NOW
    )
    subscriber = RuntimeMetricsSubscriber(
        service=service
    )
    bus = DomainEventBus()

    bus.subscribe(
        DomainEventType.EXECUTION_RECORDED,
        subscriber,
    )

    result = bus.publish(
        create_event(
            "event-1",
            DomainEventType.EXECUTION_RECORDED,
        )
    )

    assert result.is_successful
    assert service.get(
        RuntimeMetricName.EXECUTION_RECORDED_COUNT
    ) == 1
