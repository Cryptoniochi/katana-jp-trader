"""Dashboard task retry設定のテスト。"""

from pathlib import Path

import app.dashboard_autostart as module


def test_generated_task_command_has_retry_settings(
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

    command_path = module._write_task_command(
        project_directory=tmp_path,
        database_path=Path(
            "data/katana.db"
        ),
        port=8000,
        host_mode="tailscale",
        log_path=Path(
            "logs/dashboard/dashboard_resident.log"
        ),
    )
    content = command_path.read_text(
        encoding="utf-8",
    )

    assert (
        "--tailscale-wait-attempts 60"
        in content
    )
    assert "--max-restarts 100" in content
    assert (
        "--restart-delay-seconds 10"
        in content
    )
