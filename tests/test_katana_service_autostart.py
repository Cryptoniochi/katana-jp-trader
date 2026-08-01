"""KATANA Service自動起動タスクのテスト。"""

from pathlib import Path

import app.katana_service_autostart as module


def test_task_command_starts_service_manager(
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
    content = command_path.read_text(
        encoding="utf-8",
    )

    assert "app.run_katana_service" in content
    assert "app.run_dashboard_resident" not in content
    assert "--enable-paper-trading" not in content
