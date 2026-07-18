"""BrokerRecoveryServiceのテスト。"""

from datetime import datetime, timedelta, timezone

from app.broker.broker_health_models import (
    BrokerHealthCheckResult,
    BrokerHealthStatus,
)
from app.runtime.broker_recovery_service import (
    BrokerRecoveryService,
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


def create_service(
    clock: Clock,
    health_service: FakeHealthService,
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
