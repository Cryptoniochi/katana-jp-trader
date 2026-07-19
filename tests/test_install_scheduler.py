"""Windowsタスク登録CLIのテスト。"""

from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from app.install_scheduler import (
    build_create_command,
    run,
)
from app.scheduler_task import SchedulerTaskSettings


def settings(tmp_path: Path):
    python = tmp_path / "python.exe"
    python.write_text("", encoding="utf-8")
    project = tmp_path / "katana"
    project.mkdir()

    return SchedulerTaskSettings(
        task_name="Project KATANA",
        python_executable=python,
        project_root=project,
        start_time="08:55",
    )


def test_create_command_contains_schedule(
    tmp_path: Path,
) -> None:
    command = build_create_command(
        settings(tmp_path),
        force=True,
    )

    assert command[0] == "powershell.exe"
    script = command[-1]
    assert "New-ScheduledTaskAction" in script
    assert "Monday" in script
    assert "Friday" in script
    assert "08:55" in script
    assert "-RestartCount 3" in script
    assert "-Minutes 5" in script
    assert "-MultipleInstances IgnoreNew" in script
    assert " -Force" in script


def test_dry_run_does_not_execute(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.install_scheduler.sys.platform",
        "win32",
    )
    calls = []

    exit_code = run(
        ["--dry-run"],
        output=StringIO(),
        error_output=StringIO(),
        command_runner=(
            lambda *args, **kwargs: calls.append(1)
        ),
        settings_factory=(
            lambda **kwargs: settings(tmp_path)
        ),
    )

    assert exit_code == 0
    assert calls == []


def test_successful_registration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.install_scheduler.sys.platform",
        "win32",
    )

    exit_code = run(
        [],
        output=StringIO(),
        error_output=StringIO(),
        command_runner=(
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0,
                stdout="SUCCESS",
                stderr="",
            )
        ),
        settings_factory=(
            lambda **kwargs: settings(tmp_path)
        ),
    )

    assert exit_code == 0
