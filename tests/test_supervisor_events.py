"""SupervisorEventPublisherのテスト。"""

from datetime import datetime, timezone

from app.events.domain_event_bus import DomainEventBus
from app.events.domain_events import DomainEventType
from app.supervisor.supervisor_events import (
    SupervisorEventPublisher,
)
from app.supervisor.supervisor_models import (
    SupervisorSnapshot,
    SupervisorStatus,
    SupervisorStopReason,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def snapshot(
    status: SupervisorStatus,
) -> SupervisorSnapshot:
    return SupervisorSnapshot(
        worker_name="live-worker",
        status=status,
        started_at=NOW,
        checked_at=NOW,
        last_heartbeat_at=NOW,
        last_restart_at=None,
        restart_count=1,
        stop_reason=(
            SupervisorStopReason.ERROR
            if status is SupervisorStatus.FAILED
            else (
                SupervisorStopReason.HEARTBEAT_TIMEOUT
                if status is SupervisorStatus.STALE
                else None
            )
        ),
        message=None,
    )


def test_publisher_emits_supervisor_domain_event() -> None:
    bus = DomainEventBus()
    received = []
    bus.subscribe(
        DomainEventType.ERROR_OCCURRED,
        received.append,
    )
    publisher = SupervisorEventPublisher(
        event_bus=bus,
        event_id_provider=lambda: "supervisor-event-1",
    )

    result = publisher.publish(
        snapshot(SupervisorStatus.FAILED)
    )

    assert result.is_successful
    assert len(received) == 1
    event = received[0]
    assert event.event_id == "supervisor-event-1"
    assert event.payload["severity"] == "critical"
    assert event.payload["worker_name"] == "live-worker"
    assert event.payload["restart_count"] == 1


def test_stale_maps_to_error_severity() -> None:
    bus = DomainEventBus()
    received = []
    bus.subscribe(
        DomainEventType.ERROR_OCCURRED,
        received.append,
    )
    publisher = SupervisorEventPublisher(
        event_bus=bus,
        event_id_provider=lambda: "supervisor-event-2",
    )

    publisher.publish(
        snapshot(SupervisorStatus.STALE)
    )

    assert received[0].payload["severity"] == "error"
    assert received[0].correlation_id == (
        "supervisor-live-worker"
    )
