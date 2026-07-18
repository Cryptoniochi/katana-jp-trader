"""Tests for BrokerRecoveryService."""

from datetime import datetime, timedelta, timezone

from app.broker.broker_health_models import (
    BrokerHealthCheckResult,
    BrokerHealthStatus,
)
from app.runtime.broker_recovery_service import (
    BrokerRecoveryService,
)
from app.runtime.recovery_event_models import (
    RecoveryEvent,
    RecoveryEventCategory,
    RecoveryEventStatus,
    RecoverySource,
)
from app.runtime.recovery_models import (
    RecoveryPolicy,
)
from app.runtime.recovery_service import (
    RecoveryService,
)


START = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class Clock:
    def __init__(self) -> None:
        self.current = START

    def now(self) -> datetime:
        value = self.current
        self.current += timedelta(milliseconds=1)
        return value


class FakeBroker:
    broker_name = "fake"

    def __init__(self, *, healthy: bool) -> None:
        self.healthy = healthy


class FakeHealthService:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.calls = 0

    def check(
        self,
        broker: FakeBroker,
    ) -> BrokerHealthCheckResult:
        self.calls += 1
        healthy = broker.healthy

        return BrokerHealthCheckResult(
            broker_name=broker.broker_name,
            status=(
                BrokerHealthStatus.HEALTHY
                if healthy
                else BrokerHealthStatus.UNAVAILABLE
            ),
            checked_at=self.clock.now(),
            account_accessible=healthy,
            orders_accessible=healthy,
            positions_accessible=healthy,
            active_order_count=0,
            position_count=0,
            error_messages=(
                ()
                if healthy
                else ("broker unavailable",)
            ),
        )


class FakeRecoveryEventRecorder:
    """Collect recorded recovery events."""

    def __init__(self) -> None:
        self.events: list[RecoveryEvent] = []

    def record(
        self,
        event: RecoveryEvent,
    ) -> RecoveryEvent:
        self.events.append(event)
        return event


def create_service(
    clock: Clock,
    health_service: FakeHealthService,
    *,
    event_recorder: (
        FakeRecoveryEventRecorder | None
    ) = None,
) -> BrokerRecoveryService:
    return BrokerRecoveryService(
        health_service=health_service,
        recovery_service=RecoveryService(
            policy=RecoveryPolicy(
                maximum_attempts=3,
                initial_delay_seconds=0.0,
                backoff_multiplier=1.0,
                maximum_delay_seconds=0.0,
            ),
            now_provider=clock.now,
            sleeper=lambda _seconds: None,
        ),
        event_recorder=event_recorder,
    )


def test_healthy_broker_skips_recovery() -> None:
    clock = Clock()
    health_service = FakeHealthService(clock)
    broker = FakeBroker(healthy=True)
    reconnect_calls = []

    result = create_service(
        clock,
        health_service,
    ).recover_if_needed(
        broker=broker,
        reconnect_action=lambda: reconnect_calls.append(
            True
        ),
    )

    assert reconnect_calls == []
    assert health_service.calls == 1
    assert result.recovered is True


def test_unavailable_broker_is_recovered() -> None:
    clock = Clock()
    health_service = FakeHealthService(clock)
    broker = FakeBroker(healthy=False)
    reconnect_calls = []

    def reconnect() -> bool:
        reconnect_calls.append(True)
        broker.healthy = True
        return True

    result = create_service(
        clock,
        health_service,
    ).recover_if_needed(
        broker=broker,
        reconnect_action=reconnect,
    )

    assert reconnect_calls == [True]
    assert health_service.calls == 2
    assert result.recovery_attempted is True
    assert result.recovered is True
    assert result.final_health.is_healthy


def test_failed_recovery_remains_unavailable() -> None:
    clock = Clock()
    health_service = FakeHealthService(clock)
    broker = FakeBroker(healthy=False)

    result = create_service(
        clock,
        health_service,
    ).recover_if_needed(
        broker=broker,
        reconnect_action=lambda: False,
    )

    assert result.recovery_attempted is True
    assert result.recovered is False
    assert result.final_health.is_unavailable
    assert result.recovery_result is not None
    assert result.recovery_result.attempt_count == 3


def test_successful_recovery_records_broker_event() -> None:
    clock = Clock()
    health_service = FakeHealthService(clock)
    broker = FakeBroker(healthy=False)
    event_recorder = FakeRecoveryEventRecorder()

    def reconnect() -> bool:
        broker.healthy = True
        return True

    result = create_service(
        clock,
        health_service,
        event_recorder=event_recorder,
    ).recover_if_needed(
        broker=broker,
        reconnect_action=reconnect,
    )

    assert result.recovery_result is not None
    assert len(event_recorder.events) == 1

    event = event_recorder.events[0]

    assert event.source is RecoverySource.BROKER
    assert (
        event.category
        is RecoveryEventCategory.RECONNECT
    )
    assert (
        event.status
        is RecoveryEventStatus.SUCCEEDED
    )
    assert event.name == "fake reconnect"


def test_failed_recovery_records_broker_event() -> None:
    clock = Clock()
    health_service = FakeHealthService(clock)
    broker = FakeBroker(healthy=False)
    event_recorder = FakeRecoveryEventRecorder()

    result = create_service(
        clock,
        health_service,
        event_recorder=event_recorder,
    ).recover_if_needed(
        broker=broker,
        reconnect_action=lambda: False,
    )

    assert result.recovery_result is not None
    assert len(event_recorder.events) == 1

    event = event_recorder.events[0]

    assert event.source is RecoverySource.BROKER
    assert (
        event.status
        is RecoveryEventStatus.FAILED
    )
    assert (
        event.metadata["attempt_count"]
        == 3
    )


def test_healthy_broker_does_not_record_event() -> None:
    clock = Clock()
    health_service = FakeHealthService(clock)
    broker = FakeBroker(healthy=True)
    event_recorder = FakeRecoveryEventRecorder()

    result = create_service(
        clock,
        health_service,
        event_recorder=event_recorder,
    ).recover_if_needed(
        broker=broker,
        reconnect_action=lambda: True,
    )

    assert result.recovery_attempted is False
    assert event_recorder.events == []
