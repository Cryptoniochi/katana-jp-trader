"""Runtime Sessionの最新活動時刻テスト。"""

from datetime import datetime, timedelta, timezone

from app.runtime.session_service import RuntimeSessionService


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
        return self.current


def test_session_records_cycle_and_heartbeat_times() -> None:
    clock = Clock()
    service = RuntimeSessionService(
        now_provider=clock.now,
        session_id_provider=lambda: "session-1",
    )

    started = service.start()

    assert started.last_cycle_at is None
    assert started.last_heartbeat_at is None

    clock.current += timedelta(seconds=5)
    cycle = service.record_cycle(successful=True)

    assert cycle.last_cycle_at == clock.current
    assert cycle.last_heartbeat_at is None

    clock.current += timedelta(seconds=3)
    heartbeat = service.record_heartbeat()

    assert heartbeat.last_cycle_at == START + timedelta(seconds=5)
    assert heartbeat.last_heartbeat_at == clock.current


def test_rotation_resets_daily_activity_times() -> None:
    clock = Clock()
    service = RuntimeSessionService(
        now_provider=clock.now,
        session_id_provider=lambda: "session-1",
    )
    service.start()
    clock.current += timedelta(seconds=5)
    service.record_cycle(successful=True)
    service.record_heartbeat()

    clock.current += timedelta(days=1)
    rotation = service.rotate_if_needed()

    assert rotation.rotated is True
    assert rotation.snapshot.last_cycle_at is None
    assert rotation.snapshot.last_heartbeat_at is None
