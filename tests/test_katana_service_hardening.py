"""KATANA Service常駐運用の堅牢化テスト。"""

import os
from pathlib import Path

import pytest

from app.runtime.katana_service_hardening import (
    ResilientKatanaServiceManager,
    ServiceAlreadyRunningError,
    ServiceInstanceLock,
)


def test_second_instance_lock_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "katana_service.lock"
    first = ServiceInstanceLock(path)
    second = ServiceInstanceLock(path)

    first.acquire()

    try:
        with pytest.raises(
            ServiceAlreadyRunningError
        ):
            second.acquire()
    finally:
        first.release()


def test_lock_can_be_reacquired(
    tmp_path: Path,
) -> None:
    path = tmp_path / "katana_service.lock"
    first = ServiceInstanceLock(path)
    second = ServiceInstanceLock(path)

    first.acquire()
    first.release()
    second.acquire()
    second.release()


def test_status_write_failure_is_non_fatal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = ResilientKatanaServiceManager(
        definitions=(),
        status_path=tmp_path / "status.json",
        status_write_attempts=2,
        status_write_retry_seconds=0,
    )

    def fail_replace(_source, _target):
        raise PermissionError("locked")

    monkeypatch.setattr(
        os,
        "replace",
        fail_replace,
    )

    assert manager.write_status() is False

    diagnostic = (
        tmp_path
        / "katana_service_manager_errors.log"
    )
    assert diagnostic.exists()
    assert "PermissionError" in (
        diagnostic.read_text(
            encoding="utf-8"
        )
    )


def test_status_write_succeeds(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "status.json"
    manager = ResilientKatanaServiceManager(
        definitions=(),
        status_path=status_path,
    )

    assert manager.write_status() is True
    assert status_path.exists()
