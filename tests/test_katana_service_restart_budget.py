# -*- coding: utf-8 -*-
# Sprint 134-2: stable-runtime restart budget reset のテスト。

from __future__ import annotations

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


NOW = datetime(2026, 9, 5, tzinfo=timezone.utc)


class FakeProcess:
    def __init__(self, *, pid: int, returncode=None) -> None:
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


class MutableMonotonic:
    def __init__(self, value: float) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def _build_manager(
    tmp_path: Path,
    *,
    clock: MutableMonotonic,
    process: FakeProcess,
    maximum_restarts: int = 2,
    reset_after_seconds: float = 3600.0,
) -> KatanaServiceManager:
    return KatanaServiceManager(
        definitions=(
            ManagedProcessDefinition(
                name=ManagedComponentName.UNIVERSE_DAILY_SCHEDULER,
                command=(
                    "python",
                    "-m",
                    "app.run_universe_daily_scheduler",
                ),
                enabled=True,
                restart_on_failure=True,
                restart_delay_seconds=30.0,
                maximum_restarts=maximum_restarts,
                restart_budget_reset_after_seconds=reset_after_seconds,
            ),
        ),
        status_path=tmp_path / "status.json",
        now_provider=lambda: NOW,
        monotonic_provider=clock,
        popen_factory=lambda *_args, **_kwargs: process,
        readiness_probe=None,
    )


def test_restart_budget_resets_after_stable_runtime(
    tmp_path: Path,
) -> None:
    clock = MutableMonotonic(100.0)
    process = FakeProcess(pid=1234)
    manager = _build_manager(
        tmp_path,
        clock=clock,
        process=process,
        maximum_restarts=2,
        reset_after_seconds=60.0,
    )

    manager.start_enabled_components()
    component = manager._components[
        ManagedComponentName.UNIVERSE_DAILY_SCHEDULER
    ]
    component.restart_count = 2

    clock.value = 161.0
    manager.poll_once()

    status = manager.create_status().components[0]
    assert status.state is ManagedComponentState.RUNNING
    assert status.restart_count == 0


def test_stable_runtime_restores_restart_capacity_before_failure(
    tmp_path: Path,
) -> None:
    clock = MutableMonotonic(100.0)
    process = FakeProcess(pid=1234)
    manager = _build_manager(
        tmp_path,
        clock=clock,
        process=process,
        maximum_restarts=2,
        reset_after_seconds=60.0,
    )

    manager.start_enabled_components()
    component = manager._components[
        ManagedComponentName.UNIVERSE_DAILY_SCHEDULER
    ]
    component.restart_count = 2

    clock.value = 161.0
    process.returncode = 1
    manager.poll_once()

    status = manager.create_status().components[0]
    assert status.state is ManagedComponentState.RESTART_WAIT
    assert status.restart_count == 0
    assert status.last_exit_code == 1


def test_short_lived_crash_does_not_reset_restart_budget(
    tmp_path: Path,
) -> None:
    clock = MutableMonotonic(100.0)
    process = FakeProcess(pid=1234)
    manager = _build_manager(
        tmp_path,
        clock=clock,
        process=process,
        maximum_restarts=2,
        reset_after_seconds=60.0,
    )

    manager.start_enabled_components()
    component = manager._components[
        ManagedComponentName.UNIVERSE_DAILY_SCHEDULER
    ]
    component.restart_count = 2

    clock.value = 130.0
    process.returncode = 1
    manager.poll_once()

    status = manager.create_status().components[0]
    assert status.state is ManagedComponentState.FAILED
    assert status.restart_count == 2
    assert status.last_exit_code == 1


def test_restart_budget_reset_interval_must_be_positive() -> None:
    try:
        ManagedProcessDefinition(
            name=ManagedComponentName.UNIVERSE_DAILY_SCHEDULER,
            command=("python",),
            enabled=True,
            restart_budget_reset_after_seconds=0.0,
        )
    except ValueError as error:
        assert "回復時間" in str(error)
    else:
        raise AssertionError("zero reset interval must be rejected")
