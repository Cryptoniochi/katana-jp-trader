from pathlib import Path

import app.katana_service_autostart as module


def test_generated_cmd_uses_resilient_service_entrypoint(
    tmp_path: Path,
) -> None:
    python_path = tmp_path / ".venv" / "Scripts" / "python.exe"
    python_path.parent.mkdir(parents=True)
    python_path.touch()

    command_path = module.write_task_command(
        project_directory=tmp_path,
    )
    content = command_path.read_text(encoding="utf-8")

    assert "-m app.run_katana_service_resilient" in content
    assert "-m app.run_katana_service " not in content


def test_task_settings_include_restart_and_power_resilience(
    monkeypatch,
) -> None:
    captured = {}

    def fake_run(arguments, **kwargs):
        captured["arguments"] = arguments
        captured["kwargs"] = kwargs

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module._set_unlimited_execution_time(
        "Project KATANA Service"
    )

    arguments = captured["arguments"]
    script = arguments[arguments.index("-Command") + 1]

    assert "$settings.ExecutionTimeLimit = 'PT0S'" in script
    assert "$settings.RestartCount = 3" in script
    assert "$settings.RestartInterval = 'PT1M'" in script
    assert (
        "$settings.DisallowStartIfOnBatteries = $false"
        in script
    )
    assert (
        "$settings.StopIfGoingOnBatteries = $false"
        in script
    )
