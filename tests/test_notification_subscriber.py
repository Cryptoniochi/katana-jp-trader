"""NotificationSubscriberのテスト。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.events.domain_event_bus import DomainEventBus
from app.events.domain_events import (
    DomainEvent,
    DomainEventType,
)
from app.notifications.notification_models import (
    NotificationSeverity,
)
from app.notifications.notification_service import (
    NotificationService,
)
from app.notifications.notification_subscriber import (
    NotificationSubscriber,
)


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


class CollectingChannel:
    channel_name = "collector"

    def __init__(self) -> None:
        self.messages = []

    def send(self, message) -> None:
        self.messages.append(message)


def create_subscriber(
    *,
    event_types=None,
):
    channel = CollectingChannel()
    service = NotificationService(
        channels=(channel,)
    )
    subscriber = NotificationSubscriber(
        service=service,
        event_types=event_types,
    )
    return subscriber, channel


def test_subscriber_converts_error_event() -> None:
    subscriber, channel = create_subscriber()

    subscriber(
        DomainEvent(
            event_id="event-1",
            event_type=DomainEventType.ERROR_OCCURRED,
            occurred_at=NOW,
            source="broker",
            payload={"message": "connection failed"},
        )
    )

    notification = channel.messages[0]
    assert notification.severity is NotificationSeverity.ERROR
    assert notification.body == "connection failed"


def test_subscriber_maps_risk_halt_to_critical() -> None:
    subscriber, channel = create_subscriber()

    subscriber(
        DomainEvent(
            event_id="event-2",
            event_type=DomainEventType.RISK_ASSESSED,
            occurred_at=NOW,
            source="risk",
            payload={
                "decision": "halted",
                "message": "daily loss limit",
            },
        )
    )

    assert channel.messages[0].severity is (
        NotificationSeverity.CRITICAL
    )


def test_subscriber_filters_event_types() -> None:
    subscriber, channel = create_subscriber(
        event_types=frozenset(
            {DomainEventType.ERROR_OCCURRED}
        )
    )

    subscriber(
        DomainEvent(
            event_id="event-3",
            event_type=DomainEventType.ORDER_CREATED,
            occurred_at=NOW,
            source="order",
        )
    )

    assert channel.messages == []


def test_subscriber_works_as_event_bus_handler() -> None:
    subscriber, channel = create_subscriber()
    bus = DomainEventBus()
    bus.subscribe(
        DomainEventType.RECOVERY_COMPLETED,
        subscriber,
    )

    result = bus.publish(
        DomainEvent(
            event_id="event-4",
            event_type=(
                DomainEventType.RECOVERY_COMPLETED
            ),
            occurred_at=NOW,
            source="recovery",
            payload={
                "has_errors": True,
                "message": "recovery completed",
            },
        )
    )

    assert result.is_successful
    assert channel.messages[0].severity is (
        NotificationSeverity.WARNING
    )
