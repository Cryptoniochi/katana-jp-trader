"""Self-Healing Service Managerのテスト。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.runtime.katana_service_manager import (
    KatanaServiceManager,
    ManagedProcessDefinition,
)
from app.runtime.katana_service_models import (
    ManagedComponentName,
    ManagedComponentState,
    ServiceEventType,
)


NOW = datetime(
    2026,
    8,
    1,
    tzinfo=timezone.utc,
)


class FakeProcess:
    def __init__(
        self,
        *,
        pid: int,
        returncode=None,
    ) -> None:
        self.pid = pid
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


def test_status_contains_uptime_and_start_event(
    tmp_path: Path,
) -> None:
    current_time = NOW
    process = FakeProcess(pid=101)

    def now_provider() -> datetime:
        return current_time

    manager = KatanaServiceManager(
        definitions=(
            ManagedProcessDefinition(
                name=ManagedComponentName.DASHBOARD,
                command=("python",),
                enabled=True,
            ),
        ),
        status_path=tmp_path / "status.json",
        now_provider=now_provider,
        popen_factory=lambda *_args, **_kwargs: process,
    )
    manager.start_enabled_components()
    current_time = NOW + timedelta(seconds=65)
    status = manager.create_status()

    assert status.uptime_seconds == 65
    assert any(
        event.event_type
        is ServiceEventType.SERVICE_STARTED
        for event in status.recent_events
    )
    assert any(
        event.event_type
        is ServiceEventType.COMPONENT_STARTED
        for event in status.recent_events
    )


def test_restart_events_are_recorded(
    tmp_path: Path,
) -> None:
    processes = [
        FakeProcess(pid=101),
        FakeProcess(pid=102),
    ]

    manager = KatanaServiceManager(
        definitions=(
            ManagedProcessDefinition(
                name=ManagedComponentName.DASHBOARD,
                command=("python",),
                enabled=True,
                restart_delay_seconds=0,
            ),
        ),
        status_path=tmp_path / "status.json",
        now_provider=lambda: NOW,
        monotonic_provider=lambda: 100.0,
        popen_factory=lambda *_args, **_kwargs: (
            processes.pop(0)
        ),
    )
    manager.start_enabled_components()

    first = manager._components[
        ManagedComponentName.DASHBOARD
    ].process
    first.returncode = 1

    manager.poll_once()
    assert manager.create_status().components[0].state is (
        ManagedComponentState.RESTART_WAIT
    )

    manager.poll_once()
    events = manager.create_status().recent_events

    assert any(
        event.event_type
        is ServiceEventType.RESTART_SCHEDULED
        for event in events
    )
    assert any(
        event.event_type
        is ServiceEventType.RESTART_COMPLETED
        for event in events
    )
