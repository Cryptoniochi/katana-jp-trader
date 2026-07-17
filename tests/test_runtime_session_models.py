"""Runtime Sessionモデルのテスト。"""

from datetime import date, datetime, timezone

import pytest

from app.runtime.session_models import (
    RuntimeDailySummary,
    RuntimeSessionSnapshot,
    RuntimeSessionStatus,
)


NOW = datetime(2026, 7, 18, tzinfo=timezone.utc)


def test_daily_summary_calculates_duration_and_success_rate() -> None:
    summary = RuntimeDailySummary(
        session_id="session-1",
        operating_date=date(2026, 7, 18),
        started_at=NOW,
        ended_at=NOW.replace(hour=1),
        cycle_count=4,
        successful_cycle_count=3,
        failed_cycle_count=1,
        heartbeat_count=10,
        restart_count=1,
        error_count=1,
    )

    assert summary.duration_seconds == 3600.0
    assert summary.success_rate == 0.75


def test_daily_summary_rejects_inconsistent_cycles() -> None:
    with pytest.raises(ValueError, match="一致しません"):
        RuntimeDailySummary(
            session_id="session-1",
            operating_date=date(2026, 7, 18),
            started_at=NOW,
            ended_at=NOW,
            cycle_count=2,
            successful_cycle_count=2,
            failed_cycle_count=1,
            heartbeat_count=0,
            restart_count=0,
            error_count=0,
        )


def test_running_snapshot_calculates_uptime() -> None:
    snapshot = RuntimeSessionSnapshot(
        session_id="session-1",
        status=RuntimeSessionStatus.RUNNING,
        started_at=NOW,
        checked_at=NOW.replace(minute=5),
        active_date=date(2026, 7, 18),
        cycle_count=0,
        successful_cycle_count=0,
        failed_cycle_count=0,
        heartbeat_count=0,
        restart_count=0,
        error_count=0,
        completed_day_count=0,
    )

    assert snapshot.is_running
    assert snapshot.uptime_seconds == 300.0
