"""SupervisorServiceのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.supervisor.supervisor_models import (
    SupervisorPolicy,
    SupervisorStatus,
    SupervisorStopReason,
)
from app.supervisor.supervisor_service import (
    SupervisorService,
)


BASE_TIME = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class Clock:
    def __init__(self) -> None:
        self.current = BASE_TIME

    def __call__(self) -> datetime:
        return self.current


def create_service(
    clock: Clock,
    *,
    timeout: float = 60.0,
    cooldown: float = 30.0,
    maximum_restart_count: int = 2,
) -> SupervisorService:
    return SupervisorService(
        worker_name="live-worker",
        policy=SupervisorPolicy(
            heartbeat_timeout_seconds=timeout,
            restart_cooldown_seconds=cooldown,
            maximum_restart_count=maximum_restart_count,
        ),
        now_provider=clock,
    )


def test_start_and_heartbeat() -> None:
    clock = Clock()
    service = create_service(clock)

    started = service.start()
    clock.current += timedelta(seconds=10)
    heartbeat = service.record_heartbeat()

    assert started.status is SupervisorStatus.RUNNING
    assert heartbeat.status is SupervisorStatus.RUNNING
    assert heartbeat.last_heartbeat_at == clock.current
    assert heartbeat.uptime_seconds == 10.0


def test_check_marks_stale_after_timeout() -> None:
    clock = Clock()
    service = create_service(
        clock,
        timeout=30.0,
    )
    service.start()
    clock.current += timedelta(seconds=31)

    snapshot = service.check()

    assert snapshot.status is SupervisorStatus.STALE
    assert snapshot.stop_reason is (
        SupervisorStopReason.HEARTBEAT_TIMEOUT
    )
    assert snapshot.requires_attention


def test_normal_stop_is_not_restart_target() -> None:
    clock = Clock()
    service = create_service(clock)
    service.start()
    service.stop(
        reason=SupervisorStopReason.NORMAL
    )

    decision = service.restart_decision()

    assert decision.should_restart is False


def test_failed_worker_can_restart_after_cooldown() -> None:
    clock = Clock()
    service = create_service(
        clock,
        cooldown=30.0,
    )
    service.start()
    service.stop(
        reason=SupervisorStopReason.ERROR,
        message="worker crashed",
    )

    decision = service.restart_decision()

    assert decision.should_restart
    assert decision.next_restart_at == (
        clock.current + timedelta(seconds=30)
    )

    with pytest.raises(
        RuntimeError,
        match="Cooldown",
    ):
        service.mark_restarted()

    clock.current += timedelta(seconds=30)
    snapshot = service.mark_restarted()

    assert snapshot.status is SupervisorStatus.RUNNING
    assert snapshot.restart_count == 1
    assert snapshot.last_restart_at == clock.current


def test_restart_limit_prevents_additional_restart() -> None:
    clock = Clock()
    service = create_service(
        clock,
        cooldown=0.0,
        maximum_restart_count=1,
    )
    service.start()
    service.stop(
        reason=SupervisorStopReason.ERROR
    )
    service.mark_restarted()
    service.stop(
        reason=SupervisorStopReason.ERROR
    )

    decision = service.restart_decision()

    assert decision.should_restart is False
    assert decision.reason is (
        SupervisorStopReason.RESTART_LIMIT
    )
    assert service.snapshot().status is (
        SupervisorStatus.FAILED
    )


def test_record_heartbeat_before_start_is_rejected() -> None:
    clock = Clock()
    service = create_service(clock)

    with pytest.raises(
        RuntimeError,
        match="開始前",
    ):
        service.record_heartbeat()


def test_naive_clock_is_rejected() -> None:
    service = SupervisorService(
        worker_name="worker",
        now_provider=lambda: datetime(2026, 7, 18),
    )

    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        service.start()
