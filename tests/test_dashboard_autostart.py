"""Dashboard auto-start task CLIのテスト。"""

from pathlib import Path

import app.dashboard_autostart as module


def test_parser_accepts_install_arguments() -> None:
    arguments = module.build_argument_parser().parse_args(
        [
            "install",
            "--project-directory",
            "C:/projects/katana",
            "--host-mode",
            "tailscale",
            "--port",
            "8000",
        ]
    )

    assert arguments.command == "install"
    assert arguments.project_directory == Path(
        "C:/projects/katana"
    )
    assert arguments.host_mode == "tailscale"
    assert arguments.port == 8000


def test_write_task_command_creates_cmd(
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
        database_path=Path("data/katana.db"),
        port=8000,
        host_mode="tailscale",
        log_path=Path(
            "logs/dashboard/dashboard_resident.log"
        ),
    )

    content = command_path.read_text(
        encoding="utf-8",
    )

    assert "app.run_dashboard_resident" in content
    assert "--host-mode tailscale" in content
    assert "dashboard_resident.log" in content
