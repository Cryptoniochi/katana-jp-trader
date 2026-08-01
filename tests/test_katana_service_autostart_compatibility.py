"""旧write_task_command APIとの互換性テスト。"""

from pathlib import Path

import app.katana_service_autostart as module


def test_write_task_command_returns_fixed_cmd(
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

    result = module.write_task_command(
        project_directory=tmp_path,
        database_path=Path("data/katana.db"),
        dashboard_port=8000,
        log_path=Path(
            "logs/service/katana_service.log"
        ),
    )

    assert result == command.resolve()
