from pathlib import Path

from app.katana_service_autostart import write_task_command


def test_generated_cmd_runs_maintenance_before_service_redirection(
    tmp_path: Path,
) -> None:
    python_path = tmp_path / ".venv" / "Scripts" / "python.exe"
    python_path.parent.mkdir(parents=True)
    python_path.touch()

    command_path = write_task_command(
        project_directory=tmp_path,
    )
    content = command_path.read_text(encoding="utf-8")

    maintenance = "-m app.run_operational_maintenance"
    service = "-m app.run_katana_service"

    assert maintenance in content
    assert service in content
    assert content.index(maintenance) < content.index(service)
    assert "if errorlevel 1 (" in content
