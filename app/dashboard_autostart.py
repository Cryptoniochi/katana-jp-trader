"""Dashboard常駐用Windowsタスクを登録・削除するCLI。"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


DEFAULT_TASK_NAME = "Project KATANA Dashboard"
DEFAULT_LOG_PATH = Path(
    "logs/dashboard/dashboard_resident.log"
)


class DashboardTaskError(RuntimeError):
    """Dashboardタスク操作に失敗したことを表す。"""


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Project KATANA Dashboardの自動起動タスクを管理します。"
        )
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    install = subparsers.add_parser("install")
    install.add_argument(
        "--task-name",
        default=DEFAULT_TASK_NAME,
    )
    install.add_argument(
        "--project-directory",
        type=Path,
        default=Path.cwd(),
    )
    install.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    install.add_argument(
        "--port",
        type=int,
        default=8000,
    )
    install.add_argument(
        "--host-mode",
        choices=("tailscale", "local"),
        default="tailscale",
    )
    install.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
    )

    remove = subparsers.add_parser("remove")
    remove.add_argument(
        "--task-name",
        default=DEFAULT_TASK_NAME,
    )

    subparsers.add_parser("status")

    return parser


def _write_task_command(
    *,
    project_directory: Path,
    database_path: Path,
    port: int,
    host_mode: str,
    log_path: Path,
) -> Path:
    """Task Schedulerから実行するCMDを生成する。"""

    resolved_project = project_directory.resolve()
    resolved_log = (
        resolved_project / log_path
        if not log_path.is_absolute()
        else log_path
    )
    resolved_log.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    command_path = (
        resolved_project
        / "scripts"
        / "run_dashboard_resident_task.cmd"
    )
    command_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    python_path = (
        resolved_project
        / ".venv"
        / "Scripts"
        / "python.exe"
    )

    if not python_path.exists():
        raise DashboardTaskError(
            "仮想環境のPythonが見つかりません。 "
            f"path={python_path}"
        )

    content = (
        "@echo off\r\n"
        "setlocal\r\n"
        f'cd /d "{resolved_project}"\r\n'
        f'"{python_path}" -m app.run_dashboard_resident '
        f'--database-path "{database_path}" '
        f'--port {port} '
        f'--host-mode {host_mode} '
        f'--tailscale-wait-attempts 60 '
        f'--tailscale-wait-seconds 5 '
        f'--max-restarts 100 '
        f'--restart-delay-seconds 10 '
        f'>> "{resolved_log}" 2>&1\r\n'
        "exit /b %ERRORLEVEL%\r\n"
    )
    command_path.write_text(
        content,
        encoding="utf-8",
    )
    return command_path


def install_task(
    *,
    task_name: str,
    project_directory: Path,
    database_path: Path,
    port: int,
    host_mode: str,
    log_path: Path,
) -> None:
    """ログオン時にDashboardを起動するタスクを登録する。"""

    command_path = _write_task_command(
        project_directory=project_directory,
        database_path=database_path,
        port=port,
        host_mode=host_mode,
        log_path=log_path,
    )

    command = [
        "schtasks",
        "/Create",
        "/TN",
        task_name,
        "/TR",
        f'"{command_path}"',
        "/SC",
        "ONLOGON",
        "/DELAY",
        "0000:30",
        "/RL",
        "LIMITED",
        "/F",
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if completed.returncode != 0:
        raise DashboardTaskError(
            "Dashboard自動起動タスクを登録できませんでした。 "
            f"stderr={completed.stderr.strip()} "
            f"stdout={completed.stdout.strip()}"
        )

    print(
        "Dashboard auto-start task installed."
    )
    print(f"Task: {task_name}")
    print(f"Command: {command_path}")
    print(
        "The dashboard will start after the next Windows logon."
    )


def remove_task(
    *,
    task_name: str,
) -> None:
    """Dashboard自動起動タスクを削除する。"""

    completed = subprocess.run(
        [
            "schtasks",
            "/Delete",
            "/TN",
            task_name,
            "/F",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if completed.returncode != 0:
        raise DashboardTaskError(
            "Dashboard自動起動タスクを削除できませんでした。 "
            f"stderr={completed.stderr.strip()} "
            f"stdout={completed.stdout.strip()}"
        )

    print(
        "Dashboard auto-start task removed."
    )


def show_status() -> None:
    """既定タスクの状態を表示する。"""

    completed = subprocess.run(
        [
            "schtasks",
            "/Query",
            "/TN",
            DEFAULT_TASK_NAME,
            "/V",
            "/FO",
            "LIST",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if completed.returncode != 0:
        print(
            "Dashboard auto-start task is not installed."
        )
        return

    print(completed.stdout)


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )

    if parsed.command == "install":
        install_task(
            task_name=parsed.task_name,
            project_directory=(
                parsed.project_directory
            ),
            database_path=parsed.database_path,
            port=parsed.port,
            host_mode=parsed.host_mode,
            log_path=parsed.log_path,
        )
        return 0

    if parsed.command == "remove":
        remove_task(
            task_name=parsed.task_name,
        )
        return 0

    show_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
