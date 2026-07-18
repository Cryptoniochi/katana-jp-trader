"""Runtime Session JSONへ活動時刻を含めるテスト。"""

from datetime import datetime, timedelta, timezone

from app.runtime.session_models import (
    RuntimeSessionSnapshot,
    RuntimeSessionStatus,
)
from app.runtime.session_report import (
    runtime_session_snapshot_to_dict,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    10,
    tzinfo=timezone.utc,
)


def test_snapshot_report_contains_activity_times() -> None:
    snapshot = RuntimeSessionSnapshot(
        session_id="session-1",
        status=RuntimeSessionStatus.RUNNING,
        started_at=NOW - timedelta(hours=1),
        checked_at=NOW,
        active_date=NOW.date(),
        cycle_count=1,
        successful_cycle_count=1,
        failed_cycle_count=0,
        heartbeat_count=1,
        restart_count=0,
        error_count=0,
        completed_day_count=0,
        last_heartbeat_at=NOW - timedelta(seconds=10),
        last_cycle_at=NOW - timedelta(seconds=20),
    )

    payload = runtime_session_snapshot_to_dict(snapshot)

    assert payload["last_heartbeat_at"] == (
        NOW - timedelta(seconds=10)
    ).isoformat()
    assert payload["last_cycle_at"] == (
        NOW - timedelta(seconds=20)
    ).isoformat()
