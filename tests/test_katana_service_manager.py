"""KatanaServiceManagerのテスト。"""

from datetime import datetime, timezone
from pathlib import Path

from app.runtime.katana_service_manager import (
    KatanaServiceManager,
    ManagedProcessDefinition,
)
from app.runtime.katana_service_models import (
    ManagedComponentName,
    ManagedComponentState,
)


NOW = datetime(
    2026,
    8,
    3,
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
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


def test_manager_starts_enabled_component(
    tmp_path: Path,
) -> None:
    created = []

    def popen_factory(command, **_kwargs):
        created.append(command)
        return FakeProcess(pid=1234)

    manager = KatanaServiceManager(
        definitions=(
            ManagedProcessDefinition(
                name=ManagedComponentName.DASHBOARD,
                command=("python", "-m", "dashboard"),
                enabled=True,
            ),
            ManagedProcessDefinition(
                name=ManagedComponentName.PAPER_TRADING,
                command=("python", "-m", "paper"),
                enabled=False,
            ),
        ),
        status_path=tmp_path / "status.json",
        now_provider=lambda: NOW,
        popen_factory=popen_factory,
    )

    manager.start_enabled_components()
    status = manager.create_status()

    assert created == [
        ["python", "-m", "dashboard"]
    ]
    rows = {
        item.name: item
        for item in status.components
    }
    assert rows[
        ManagedComponentName.DASHBOARD
    ].state is ManagedComponentState.RUNNING
    assert rows[
        ManagedComponentName.PAPER_TRADING
    ].state is ManagedComponentState.DISABLED


def test_manager_schedules_restart_after_failure(
    tmp_path: Path,
) -> None:
    process = FakeProcess(
        pid=1234,
        returncode=None,
    )

    manager = KatanaServiceManager(
        definitions=(
            ManagedProcessDefinition(
                name=ManagedComponentName.DASHBOARD,
                command=("python",),
                enabled=True,
                restart_delay_seconds=10.0,
                maximum_restarts=2,
            ),
        ),
        status_path=tmp_path / "status.json",
        now_provider=lambda: NOW,
        monotonic_provider=lambda: 100.0,
        popen_factory=lambda *_args, **_kwargs: process,
    )

    manager.start_enabled_components()
    process.returncode = 1
    manager.poll_once()
    status = manager.create_status()

    assert status.components[0].state is (
        ManagedComponentState.RESTART_WAIT
    )
    assert status.components[0].last_exit_code == 1



def test_readiness_change_handler_receives_transitions(
    tmp_path: Path,
) -> None:
    transitions = []
    probe_results = iter(
        [
            type(
                "Result",
                (),
                {
                    "state": "disconnected",
                    "message": "not logged in",
                },
            )(),
            type(
                "Result",
                (),
                {
                    "state": "connected",
                    "message": "connected",
                },
            )(),
            type(
                "Result",
                (),
                {
                    "state": "connected",
                    "message": "connected",
                },
            )(),
        ]
    )
    monotonic_values = iter(
        [0.0, 61.0, 122.0]
    )

    manager = KatanaServiceManager(
        definitions=(),
        status_path=tmp_path / "status.json",
        now_provider=lambda: NOW,
        monotonic_provider=lambda: next(
            monotonic_values
        ),
        readiness_probe=lambda: next(
            probe_results
        ),
        readiness_interval_seconds=60.0,
        readiness_change_handler=(
            lambda previous, current, message: (
                transitions.append(
                    (
                        previous,
                        current,
                        message,
                    )
                )
            )
        ),
    )

    manager.poll_once()
    manager.poll_once()
    manager.poll_once()

    assert transitions == [
        (
            "not_checked",
            "disconnected",
            "not logged in",
        ),
        (
            "disconnected",
            "connected",
            "connected",
        ),
    ]


def test_readiness_notification_failure_does_not_stop_manager(
    tmp_path: Path,
) -> None:
    manager = KatanaServiceManager(
        definitions=(),
        status_path=tmp_path / "status.json",
        now_provider=lambda: NOW,
        readiness_probe=lambda: type(
            "Result",
            (),
            {
                "state": "connected",
                "message": "connected",
            },
        )(),
        readiness_change_handler=(
            lambda *_args: (
                (_ for _ in ()).throw(
                    RuntimeError("notification failed")
                )
            )
        ),
    )

    manager.poll_once()
    status = manager.create_status()

    assert status.kabu_station_readiness == (
        "connected"
    )
    assert any(
        "notification failed" in event.message
        for event in status.recent_events
    )
