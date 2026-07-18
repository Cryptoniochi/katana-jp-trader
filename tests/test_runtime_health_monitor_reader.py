"""RuntimeHealthMonitorReaderのテスト。"""

from datetime import datetime, timedelta, timezone

from app.runtime.runtime_health_monitor_models import (
    RuntimeHealthMonitorPolicy,
    RuntimeHealthStatus,
)
from app.runtime.runtime_health_monitor_reader import (
    RuntimeHealthMonitorReader,
)
from app.runtime.runtime_health_monitor_service import (
    RuntimeHealthMonitorService,
)
from app.runtime.session_models import (
    RuntimeSessionSnapshot,
    RuntimeSessionStatus,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    10,
    tzinfo=timezone.utc,
)


class SessionReader:
    def snapshot(self) -> RuntimeSessionSnapshot:
        return RuntimeSessionSnapshot(
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
            last_heartbeat_at=NOW - timedelta(seconds=20),
            last_cycle_at=NOW - timedelta(seconds=30),
        )


def test_reader_evaluates_session_activity() -> None:
    reader = RuntimeHealthMonitorReader(
        session_reader=SessionReader(),
        monitor_service=RuntimeHealthMonitorService(
            policy=RuntimeHealthMonitorPolicy(
                heartbeat_warning_seconds=90,
                heartbeat_critical_seconds=180,
                cycle_warning_seconds=180,
                cycle_critical_seconds=300,
            )
        ),
    )

    report = reader.check()

    assert report.status is RuntimeHealthStatus.HEALTHY
    assert report.heartbeat_age_seconds == 20
    assert report.cycle_age_seconds == 30
