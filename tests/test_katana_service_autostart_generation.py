"""固定CMD自動生成を含む互換性テスト。"""

from pathlib import Path

import app.katana_service_autostart as module


def test_write_task_command_creates_missing_fixed_cmd(
    tmp_path: Path,
) -> None:
    python_path = (
        tmp_path
        / ".venv"
        / "Scripts"
        / "python.exe"
    )
    python_path.parent.mkdir(
        parents=True,
    )
    python_path.write_text(
        "",
        encoding="utf-8",
    )

    command_path = module.write_task_command(
        project_directory=tmp_path,
        database_path=Path("data/katana.db"),
        dashboard_port=8000,
        log_path=Path(
            "logs/service/katana_service.log"
        ),
    )

    assert command_path.exists()
    content = command_path.read_text(
        encoding="utf-8",
    )
    assert "app.run_katana_service" in content
    assert "--dashboard-port 8000" in content
    assert "katana_service.log" in content


def test_write_task_command_reuses_existing_fixed_cmd(
    tmp_path: Path,
) -> None:
    command_path = (
        tmp_path
        / "scripts"
        / "run_katana_service_task.cmd"
    )
    command_path.parent.mkdir(parents=True)
    command_path.write_text(
        "@echo existing",
        encoding="utf-8",
    )

    result = module.write_task_command(
        project_directory=tmp_path,
    )

    assert result == command_path.resolve()
    assert result.read_text(
        encoding="utf-8"
    ) == "@echo existing"
