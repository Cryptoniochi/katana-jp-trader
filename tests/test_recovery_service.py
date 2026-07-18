"""RecoveryServiceのテスト。"""

from datetime import datetime, timedelta, timezone

from app.runtime.recovery_models import (
    RecoveryPolicy,
    RecoveryStatus,
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


def test_service_succeeds_after_retry() -> None:
    clock = Clock()
    sleeps = []
    calls = []

    def action() -> bool:
        calls.append(len(calls) + 1)
        return len(calls) >= 2

    service = RecoveryService(
        policy=RecoveryPolicy(
            maximum_attempts=3,
            initial_delay_seconds=2.0,
            backoff_multiplier=2.0,
            maximum_delay_seconds=10.0,
        ),
        now_provider=clock.now,
        sleeper=sleeps.append,
    )

    result = service.execute(
        recovery_name="broker reconnect",
        action=action,
    )

    assert result.status is RecoveryStatus.SUCCESS
    assert result.attempt_count == 2
    assert result.attempts[0].successful is False
    assert result.attempts[1].successful is True
    assert sleeps == [2.0]
    assert result.total_delay_seconds == 2.0


def test_service_fails_after_maximum_attempts() -> None:
    clock = Clock()
    service = RecoveryService(
        policy=RecoveryPolicy(
            maximum_attempts=2,
            initial_delay_seconds=1.0,
            backoff_multiplier=2.0,
            maximum_delay_seconds=5.0,
        ),
        now_provider=clock.now,
        sleeper=lambda _seconds: None,
    )

    result = service.execute(
        recovery_name="runtime restart",
        action=lambda: False,
    )

    assert result.status is RecoveryStatus.FAILED
    assert result.attempt_count == 2
    assert result.succeeded is False


def test_service_can_abort_before_first_attempt() -> None:
    clock = Clock()
    service = RecoveryService(
        now_provider=clock.now,
        sleeper=lambda _seconds: None,
    )

    result = service.execute(
        recovery_name="runtime restart",
        action=lambda: True,
        should_abort=lambda: True,
    )

    assert result.status is RecoveryStatus.ABORTED
    assert result.attempt_count == 0
    assert result.message is not None
