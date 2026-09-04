"""Universe Daily Scheduler単一インスタンス制御のテスト。"""

import json
import os
from pathlib import Path

import pytest

from app.run_universe_daily_scheduler import (
    SchedulerAlreadyRunningError,
    UniverseDailySchedulerLock,
)


def test_lock_rejects_second_live_scheduler(tmp_path: Path) -> None:
    path = tmp_path / "scheduler.lock"
    first = UniverseDailySchedulerLock(path)
    first.acquire()

    try:
        second = UniverseDailySchedulerLock(path)
        with pytest.raises(SchedulerAlreadyRunningError):
            second.acquire()
    finally:
        first.release()

    assert not path.exists()


def test_stale_lock_is_replaced(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "scheduler.lock"
    path.write_text(
        json.dumps({"pid": 99999999}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        UniverseDailySchedulerLock,
        "_pid_is_running",
        staticmethod(lambda _pid: False),
    )

    lock = UniverseDailySchedulerLock(path)
    lock.acquire()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["pid"] == os.getpid()
    finally:
        lock.release()

    assert not path.exists()


def test_release_does_not_delete_foreign_lock(tmp_path: Path) -> None:
    path = tmp_path / "scheduler.lock"
    lock = UniverseDailySchedulerLock(path)
    lock.acquire()

    path.write_text(
        json.dumps({"pid": os.getpid() + 1000}),
        encoding="utf-8",
    )
    lock.release()

    assert path.exists()


def test_windows_pid_check_uses_windows_api(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.run_universe_daily_scheduler.sys.platform",
        "win32",
    )
    monkeypatch.setattr(
        UniverseDailySchedulerLock,
        "_windows_pid_is_running",
        staticmethod(lambda pid: pid == 12345),
    )

    assert UniverseDailySchedulerLock._pid_is_running(12345)
    assert not UniverseDailySchedulerLock._pid_is_running(54321)


def test_invalid_pid_is_not_running() -> None:
    assert not UniverseDailySchedulerLock._pid_is_running(0)
    assert not UniverseDailySchedulerLock._pid_is_running(-1)
