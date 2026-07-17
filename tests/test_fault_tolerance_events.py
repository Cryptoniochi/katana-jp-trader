"""FaultToleranceEventPublisherのテスト。"""

from datetime import datetime, timezone

from app.events.domain_event_bus import DomainEventBus
from app.events.domain_events import DomainEventType
from app.supervisor.fault_tolerance_events import (
    FaultToleranceEventPublisher,
)
from app.supervisor.fault_tolerance_models import (
    FaultToleranceAttempt,
    FaultToleranceDecision,
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


def supervisor_snapshot() -> SupervisorSnapshot:
    return SupervisorSnapshot(
        worker_name="live-worker",
        status=SupervisorStatus.FAILED,
        started_at=NOW,
        checked_at=NOW,
        last_heartbeat_at=NOW,
        last_restart_at=None,
        restart_count=2,
        stop_reason=SupervisorStopReason.ERROR,
    )


def test_publisher_emits_recovery_completed_event() -> None:
    bus = DomainEventBus()
    received = []
    bus.subscribe(
        DomainEventType.RECOVERY_COMPLETED,
        received.append,
    )
    publisher = FaultToleranceEventPublisher(
        event_bus=bus,
        event_id_provider=lambda: "fault-event-1",
    )
    snapshot = supervisor_snapshot()
    attempt = FaultToleranceAttempt(
        attempt_number=3,
        checked_at=NOW,
        decision=FaultToleranceDecision.SAFE_STOP,
        supervisor_before=snapshot,
        supervisor_after=snapshot,
        recovery_result=None,
        consecutive_failure_count=3,
        next_action_at=None,
        message="safe stop",
    )

    result = publisher.publish(attempt)

    assert result.is_successful
    assert len(received) == 1
    event = received[0]
    assert event.event_id == "fault-event-1"
    assert event.payload["severity"] == "critical"
    assert event.payload["decision"] == "safe_stop"
    assert event.payload["has_errors"] is True
    assert event.correlation_id == (
        "fault-tolerance-live-worker-3"
    )
