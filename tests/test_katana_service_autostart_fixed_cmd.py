"""固定CMD方式のKATANA Serviceタスクテスト。"""

from pathlib import Path

import app.katana_service_autostart as module


def test_resolve_task_command_uses_fixed_cmd(
    tmp_path: Path,
) -> None:
    command = (
        tmp_path
        / "scripts"
        / "run_katana_service_task.cmd"
    )
    command.parent.mkdir(parents=True)
    command.write_text(
        "@echo off",
        encoding="utf-8",
    )

    resolved = module.resolve_task_command(
        project_directory=tmp_path,
        task_command=Path(
            "scripts/run_katana_service_task.cmd"
        ),
    )

    assert resolved == command.resolve()


def test_install_uses_cmd_executable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    command = (
        tmp_path
        / "scripts"
        / "run_katana_service_task.cmd"
    )
    command.parent.mkdir(parents=True)
    command.write_text(
        "@echo off",
        encoding="utf-8",
    )
    captured = {}

    def fake_run_schtasks(
        arguments,
        *,
        failure_message,
        allow_failure=False,
    ):
        captured["arguments"] = arguments
        captured["failure_message"] = failure_message
        captured["allow_failure"] = allow_failure

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(
        module,
        "_run_schtasks",
        fake_run_schtasks,
    )

    module.install_task(
        task_name="Project KATANA Service",
        project_directory=tmp_path,
        task_command=Path(
            "scripts/run_katana_service_task.cmd"
        ),
    )

    task_run = captured["arguments"][
        captured["arguments"].index("/TR") + 1
    ]

    assert task_run.startswith(
        'cmd.exe /d /c ""'
    )
    assert str(command.resolve()) in task_run
    assert "app.run_katana_service" not in task_run
