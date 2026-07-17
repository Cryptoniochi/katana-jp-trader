"""RuntimeSessionServiceのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.runtime.session_models import (
    RuntimeSessionStatus,
    RuntimeSessionStopReason,
)
from app.runtime.session_service import RuntimeSessionService


BASE = datetime(2026, 7, 18, 23, 59, tzinfo=timezone.utc)


class Clock:
    def __init__(self) -> None:
        self.current = BASE

    def __call__(self) -> datetime:
        return self.current


def create_service(clock: Clock) -> RuntimeSessionService:
    return RuntimeSessionService(
        now_provider=clock,
        session_id_provider=lambda: "session-1",
    )


def test_start_and_record_counters() -> None:
    clock = Clock()
    service = create_service(clock)

    service.start()
    service.record_cycle(successful=True)
    service.record_cycle(successful=False)
    service.record_heartbeat()
    service.record_restart()
    service.record_error()

    snapshot = service.snapshot()

    assert snapshot.status is RuntimeSessionStatus.RUNNING
    assert snapshot.cycle_count == 2
    assert snapshot.successful_cycle_count == 1
    assert snapshot.failed_cycle_count == 1
    assert snapshot.heartbeat_count == 1
    assert snapshot.restart_count == 1
    assert snapshot.error_count == 2


def test_date_change_rotates_daily_summary() -> None:
    clock = Clock()
    service = create_service(clock)
    service.start()
    service.record_cycle(successful=True)

    clock.current += timedelta(minutes=2)
    result = service.rotate_if_needed()

    assert result.rotated
    assert result.previous_summary is not None
    assert result.previous_summary.cycle_count == 1
    assert result.snapshot.active_date.isoformat() == "2026-07-19"
    assert result.snapshot.cycle_count == 0
    assert result.snapshot.completed_day_count == 1


def test_stop_returns_final_report() -> None:
    clock = Clock()
    service = create_service(clock)
    service.start()
    service.record_cycle(successful=False)
    clock.current += timedelta(minutes=1)

    report = service.stop(
        reason=RuntimeSessionStopReason.ERROR,
        message="paper session failed",
    )

    assert report.snapshot.status is RuntimeSessionStatus.FAILED
    assert report.snapshot.stop_reason is RuntimeSessionStopReason.ERROR
    assert report.total_cycle_count == 1
    assert report.total_error_count == 1
    assert len(report.daily_summaries) == 1


def test_operations_before_start_are_rejected() -> None:
    service = create_service(Clock())

    with pytest.raises(RuntimeError):
        service.record_heartbeat()

    with pytest.raises(RuntimeError):
        service.snapshot()


def test_naive_clock_is_rejected() -> None:
    service = RuntimeSessionService(
        now_provider=lambda: datetime(2026, 7, 18),
        session_id_provider=lambda: "session-1",
    )

    with pytest.raises(ValueError, match="タイムゾーン"):
        service.start()
