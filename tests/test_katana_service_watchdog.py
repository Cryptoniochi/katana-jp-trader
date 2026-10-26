from datetime import datetime, timedelta, timezone
from pathlib import Path

import app.run_katana_service_watchdog as module


def _write_status(
    path: Path,
    generated_at: datetime,
    *,
    service_state: str = "healthy",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            '{"generated_at": "'
            + generated_at.isoformat()
            + '", "service_state": "'
            + service_state
            + '"}'
        ),
        encoding="utf-8",
    )


def test_fresh_status_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    now = datetime.now(timezone.utc)
    _write_status(path, now)
    assert module._status_is_fresh(
        path,
        stale_seconds=90,
        now=now,
    )
    assert module._status_is_healthy(
        path,
        stale_seconds=90,
        now=now,
    )


def test_stale_status_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    now = datetime.now(timezone.utc)
    _write_status(path, now - timedelta(seconds=91))
    assert not module._status_is_fresh(
        path,
        stale_seconds=90,
        now=now,
    )
    assert not module._status_is_healthy(
        path,
        stale_seconds=90,
        now=now,
    )


def test_fresh_but_unhealthy_status_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    now = datetime.now(timezone.utc)
    _write_status(path, now, service_state="degraded")
    assert module._status_is_fresh(path, stale_seconds=90, now=now)
    assert not module._status_is_healthy(path, stale_seconds=90, now=now)


def test_invalid_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    path.write_text('{"generated_at": ', encoding="utf-8")
    assert not module._status_is_fresh(path, stale_seconds=90)
    assert not module._status_is_healthy(path, stale_seconds=90)


def test_module_pattern_does_not_match_watchdog() -> None:
    pattern = module._module_command_pattern("app.run_katana_service")
    import re

    assert re.search(pattern, "python.exe -m app.run_katana_service --x")
    assert not re.search(
        pattern,
        "python.exe -m app.run_katana_service_watchdog",
    )


def test_healthy_service_does_not_recover(tmp_path, monkeypatch) -> None:
    status = tmp_path / "status.json"
    _write_status(status, datetime.now(timezone.utc))
    monkeypatch.setattr(module, "_task_state", lambda _name: "Running")

    def unexpected():
        raise AssertionError("cleanup must not run")

    monkeypatch.setattr(module, "_list_katana_process_ids", unexpected)

    result = module.check_and_recover(
        status_path=status,
        log_path=tmp_path / "watchdog.log",
        recovery_wait_seconds=0,
    )

    assert result.healthy
    assert not result.recovered


def test_unhealthy_service_is_ended_cleaned_and_restarted(
    tmp_path,
    monkeypatch,
) -> None:
    status = tmp_path / "status.json"
    _write_status(
        status,
        datetime.now(timezone.utc) - timedelta(minutes=10),
    )

    states = iter(["Ready", "Ready", "Running"])
    monkeypatch.setattr(module, "_task_state", lambda _name: next(states))

    calls = []
    monkeypatch.setattr(
        module,
        "_end_task",
        lambda name: calls.append(("end", name)) or True,
    )
    monkeypatch.setattr(
        module,
        "_list_katana_process_ids",
        lambda: calls.append(("list", None)) or [10, 20],
    )
    monkeypatch.setattr(
        module,
        "_kill_process_trees",
        lambda pids: calls.append(("kill", list(pids))),
    )
    monkeypatch.setattr(
        module,
        "_start_task",
        lambda name: calls.append(("start", name)) or True,
    )
    monkeypatch.setattr(
        module,
        "_status_is_healthy",
        lambda _path, *, stale_seconds, now=None: True,
    )

    result = module.check_and_recover(
        task_name="Project KATANA Service",
        status_path=status,
        log_path=tmp_path / "watchdog.log",
        recovery_wait_seconds=0,
        task_stop_wait_seconds=0,
    )

    assert result.healthy
    assert result.recovered
    assert calls == [
        ("end", "Project KATANA Service"),
        ("list", None),
        ("kill", [10, 20]),
        ("start", "Project KATANA Service"),
    ]


def test_fresh_unhealthy_service_triggers_recovery(
    tmp_path,
    monkeypatch,
) -> None:
    status = tmp_path / "status.json"
    _write_status(
        status,
        datetime.now(timezone.utc),
        service_state="degraded",
    )

    states = iter(["Running", "Ready", "Running"])
    monkeypatch.setattr(module, "_task_state", lambda _name: next(states))
    monkeypatch.setattr(module, "_end_task", lambda _name: True)
    monkeypatch.setattr(module, "_list_katana_process_ids", lambda: [])
    monkeypatch.setattr(module, "_kill_process_trees", lambda _pids: None)
    monkeypatch.setattr(module, "_start_task", lambda _name: True)
    monkeypatch.setattr(
        module,
        "_status_is_healthy",
        lambda _path, *, stale_seconds, now=None: True,
    )

    result = module.check_and_recover(
        status_path=status,
        log_path=tmp_path / "watchdog.log",
        recovery_wait_seconds=0,
        task_stop_wait_seconds=0,
    )

    assert result.healthy
    assert result.recovered


def test_recovery_success_requires_healthy_status(
    tmp_path,
    monkeypatch,
) -> None:
    status = tmp_path / "status.json"
    _write_status(
        status,
        datetime.now(timezone.utc) - timedelta(minutes=10),
    )

    states = iter(["Ready", "Ready", "Running"])
    monkeypatch.setattr(module, "_task_state", lambda _name: next(states))
    monkeypatch.setattr(module, "_end_task", lambda _name: True)
    monkeypatch.setattr(module, "_list_katana_process_ids", lambda: [])
    monkeypatch.setattr(module, "_kill_process_trees", lambda _pids: None)
    monkeypatch.setattr(module, "_start_task", lambda _name: True)
    monkeypatch.setattr(
        module,
        "_status_is_healthy",
        lambda _path, *, stale_seconds, now=None: False,
    )

    result = module.check_and_recover(
        status_path=status,
        log_path=tmp_path / "watchdog.log",
        recovery_wait_seconds=0,
        task_stop_wait_seconds=0,
    )

    assert not result.healthy
    assert result.recovered
    assert "timed out" in result.message


def test_recovery_exception_is_logged(tmp_path, monkeypatch) -> None:
    status = tmp_path / "status.json"
    _write_status(
        status,
        datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    monkeypatch.setattr(module, "_task_state", lambda _name: "Ready")
    monkeypatch.setattr(
        module,
        "_end_task",
        lambda _name: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    log_path = tmp_path / "watchdog.log"
    result = module.check_and_recover(
        status_path=status,
        log_path=log_path,
        recovery_wait_seconds=0,
        task_stop_wait_seconds=0,
    )

    assert not result.healthy
    assert not result.recovered
    assert "RuntimeError: boom" in result.message
    assert "RuntimeError: boom" in log_path.read_text(encoding="utf-8")
