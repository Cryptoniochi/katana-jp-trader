"""RuntimeRecoveryServiceのテスト。"""

from datetime import datetime, timedelta, timezone

from app.runtime.recovery_models import (
    RecoveryPolicy,
)
from app.runtime.recovery_service import (
    RecoveryService,
)
from app.runtime.runtime_health_monitor_models import (
    RuntimeHealthMonitorReport,
    RuntimeHealthStatus,
)
from app.runtime.runtime_recovery_service import (
    RuntimeRecoveryService,
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


class FakeHealthReader:
    def __init__(
        self,
        statuses: list[RuntimeHealthStatus],
    ) -> None:
        self.statuses = list(statuses)
        self.calls = 0

    def check(self) -> RuntimeHealthMonitorReport:
        index = min(
            self.calls,
            len(self.statuses) - 1,
        )
        status = self.statuses[index]
        self.calls += 1

        return RuntimeHealthMonitorReport(
            status=status,
            checked_at=START,
            running=(
                status
                is not RuntimeHealthStatus.STOPPED
            ),
            heartbeat_age_seconds=10.0,
            cycle_age_seconds=20.0,
            reasons=(
                ()
                if status in {
                    RuntimeHealthStatus.HEALTHY,
                    RuntimeHealthStatus.IDLE,
                }
                else ("runtime issue",)
            ),
        )


def create_service(
    health_reader: FakeHealthReader,
    clock: Clock,
    *,
    recover_warning: bool = False,
) -> RuntimeRecoveryService:
    return RuntimeRecoveryService(
        health_reader=health_reader,
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
        recover_warning=recover_warning,
    )


def test_healthy_runtime_skips_recovery() -> None:
    clock = Clock()
    health_reader = FakeHealthReader(
        [RuntimeHealthStatus.HEALTHY]
    )
    restart_calls = []

    result = create_service(
        health_reader,
        clock,
    ).recover_if_needed(
        runtime_name="paper-runtime",
        restart_action=lambda: restart_calls.append(
            True
        ),
    )

    assert restart_calls == []
    assert health_reader.calls == 1
    assert result.recovered is True


def test_critical_runtime_is_recovered() -> None:
    clock = Clock()
    health_reader = FakeHealthReader(
        [
            RuntimeHealthStatus.CRITICAL,
            RuntimeHealthStatus.HEALTHY,
        ]
    )
    restart_calls = []

    result = create_service(
        health_reader,
        clock,
    ).recover_if_needed(
        runtime_name="paper-runtime",
        restart_action=lambda: (
            restart_calls.append(True)
            or True
        ),
    )

    assert restart_calls == [True]
    assert health_reader.calls == 2
    assert result.recovery_attempted is True
    assert result.recovered is True


def test_warning_is_not_recovered_by_default() -> None:
    clock = Clock()
    health_reader = FakeHealthReader(
        [RuntimeHealthStatus.WARNING]
    )

    result = create_service(
        health_reader,
        clock,
    ).recover_if_needed(
        runtime_name="paper-runtime",
        restart_action=lambda: True,
    )

    assert result.recovery_attempted is False
    assert result.recovered is False
    assert health_reader.calls == 1


def test_warning_can_be_recovered_by_policy() -> None:
    clock = Clock()
    health_reader = FakeHealthReader(
        [
            RuntimeHealthStatus.WARNING,
            RuntimeHealthStatus.IDLE,
        ]
    )

    result = create_service(
        health_reader,
        clock,
        recover_warning=True,
    ).recover_if_needed(
        runtime_name="paper-runtime",
        restart_action=lambda: True,
    )

    assert result.recovery_attempted is True
    assert result.recovered is True
    assert result.final_health.status is (
        RuntimeHealthStatus.IDLE
    )


def test_failed_restart_remains_unhealthy() -> None:
    clock = Clock()
    health_reader = FakeHealthReader(
        [
            RuntimeHealthStatus.STOPPED,
            RuntimeHealthStatus.STOPPED,
        ]
    )

    result = create_service(
        health_reader,
        clock,
    ).recover_if_needed(
        runtime_name="paper-runtime",
        restart_action=lambda: False,
    )

    assert result.recovery_attempted is True
    assert result.recovered is False
    assert result.requires_attention is True
    assert result.recovery_result is not None
    assert result.recovery_result.attempt_count == 3
