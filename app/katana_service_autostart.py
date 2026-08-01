"""KATANA Service Manager用Windowsタスクを管理する。"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Sequence


DEFAULT_TASK_NAME = "Project KATANA Service"
LEGACY_TASK_NAME = "Project KATANA Dashboard"
DEFAULT_TASK_COMMAND = Path(
    "scripts/run_katana_service_task.cmd"
)


class KatanaServiceTaskError(RuntimeError):
    """Service自動起動タスク操作の例外。"""


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Project KATANA Serviceの自動起動タスクを管理します。"
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
        "--task-command",
        type=Path,
        default=DEFAULT_TASK_COMMAND,
    )

    remove = subparsers.add_parser("remove")
    remove.add_argument(
        "--task-name",
        default=DEFAULT_TASK_NAME,
    )

    migrate = subparsers.add_parser("migrate")
    migrate.add_argument(
        "--project-directory",
        type=Path,
        default=Path.cwd(),
    )
    migrate.add_argument(
        "--task-command",
        type=Path,
        default=DEFAULT_TASK_COMMAND,
    )

    subparsers.add_parser("status")
    return parser


def _run_schtasks(
    command: list[str],
    *,
    failure_message: str,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="mbcs",
        errors="replace",
    )

    if (
        completed.returncode != 0
        and not allow_failure
    ):
        raise KatanaServiceTaskError(
            f"{failure_message} "
            f"returncode={completed.returncode} "
            f"stderr={completed.stderr.strip()} "
            f"stdout={completed.stdout.strip()}"
        )

    return completed


def resolve_task_command(
    *,
    project_directory: Path,
    task_command: Path,
) -> Path:
    """Task Schedulerから呼び出す固定CMDの絶対パスを返す。"""

    resolved_project = project_directory.resolve()
    command_path = (
        task_command
        if task_command.is_absolute()
        else resolved_project / task_command
    )
    command_path = command_path.resolve()

    if not command_path.exists():
        raise KatanaServiceTaskError(
            "KATANA Service起動CMDが見つかりません。 "
            f"path={command_path}"
        )

    return command_path



def write_task_command(
    *,
    project_directory: Path,
    database_path: Path | None = None,
    dashboard_port: int | None = None,
    log_path: Path | None = None,
) -> Path:
    """固定CMDを必要に応じて生成し、その絶対パスを返す。

    通常運用では配布済みCMDをそのまま利用する。
    一時ディレクトリを使う既存テストや新規セットアップでは、
    ファイルが存在しない場合だけ同じ内容で生成する。
    """

    resolved_project = project_directory.resolve()
    command_path = (
        resolved_project
        / DEFAULT_TASK_COMMAND
    )
    command_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if command_path.exists():
        return command_path

    resolved_database = (
        database_path
        if database_path is not None
        else Path("data/katana.db")
    )
    resolved_port = (
        dashboard_port
        if dashboard_port is not None
        else 8000
    )
    resolved_log = (
        log_path
        if log_path is not None
        else Path(
            "logs/service/katana_service.log"
        )
    )

    log_path_value = (
        resolved_log
        if resolved_log.is_absolute()
        else resolved_project / resolved_log
    )
    log_path_value.parent.mkdir(
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
        raise KatanaServiceTaskError(
            "仮想環境のPythonが見つかりません。 "
            f"path={python_path}"
        )

    content = (
        "@echo off\r\n"
        "setlocal EnableExtensions\r\n"
        f'cd /d "{resolved_project}"\r\n'
        f'if not exist "{python_path}" (\r\n'
        "    echo ERROR: Python executable was not found.\r\n"
        "    exit /b 1\r\n"
        ")\r\n"
        f'if not exist "{log_path_value.parent}" '
        f'mkdir "{log_path_value.parent}"\r\n'
        f'"{python_path}" -m app.run_katana_service '
        f'--database-path "{resolved_database}" '
        f'--dashboard-port {resolved_port} '
        "--tailscale-wait-attempts 60 "
        "--tailscale-wait-seconds 5 "
        f'>> "{log_path_value}" 2>&1\r\n'
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
    task_command: Path,
) -> None:
    """固定CMDだけを実行するONLOGONタスクを登録する。"""

    if task_command == DEFAULT_TASK_COMMAND:
        command_path = write_task_command(
            project_directory=project_directory,
        )
    else:
        command_path = resolve_task_command(
            project_directory=project_directory,
            task_command=task_command,
        )

    # schtasks /TRではcmd.exe /d /c ""<absolute path>"" の形が
    # Windows日本語・英語環境の双方で安定する。
    task_run = (
        f'cmd.exe /d /c ""{command_path}""'
    )

    _run_schtasks(
        [
            "schtasks",
            "/Create",
            "/TN",
            task_name,
            "/TR",
            task_run,
            "/SC",
            "ONLOGON",
            "/DELAY",
            "0000:30",
            "/RL",
            "LIMITED",
            "/F",
        ],
        failure_message=(
            "KATANA Service自動起動タスクを登録できませんでした。"
        ),
    )

    print("KATANA Service auto-start task installed.")
    print(f"Task: {task_name}")
    print(f"Command: {command_path}")


def remove_task(
    *,
    task_name: str,
    ignore_missing: bool = False,
) -> None:
    """指定タスクを削除する。"""

    completed = _run_schtasks(
        [
            "schtasks",
            "/Delete",
            "/TN",
            task_name,
            "/F",
        ],
        failure_message=(
            "自動起動タスクを削除できませんでした。"
        ),
        allow_failure=ignore_missing,
    )

    if completed.returncode == 0:
        print(f"Removed task: {task_name}")


def migrate_task(
    *,
    project_directory: Path,
    task_command: Path,
) -> None:
    """旧DashboardタスクからServiceタスクへ移行する。"""

    _run_schtasks(
        [
            "schtasks",
            "/End",
            "/TN",
            LEGACY_TASK_NAME,
        ],
        failure_message=(
            "旧Dashboardタスクを停止できませんでした。"
        ),
        allow_failure=True,
    )
    _run_schtasks(
        [
            "schtasks",
            "/End",
            "/TN",
            DEFAULT_TASK_NAME,
        ],
        failure_message=(
            "既存Serviceタスクを停止できませんでした。"
        ),
        allow_failure=True,
    )

    remove_task(
        task_name=LEGACY_TASK_NAME,
        ignore_missing=True,
    )
    remove_task(
        task_name=DEFAULT_TASK_NAME,
        ignore_missing=True,
    )

    install_task(
        task_name=DEFAULT_TASK_NAME,
        project_directory=project_directory,
        task_command=task_command,
    )

    print("Legacy Dashboard task migration completed.")
    print(
        "Paper Trading remains disabled in the Service task."
    )


def show_status() -> None:
    completed = _run_schtasks(
        [
            "schtasks",
            "/Query",
            "/TN",
            DEFAULT_TASK_NAME,
            "/V",
            "/FO",
            "LIST",
        ],
        failure_message=(
            "KATANA Service自動起動タスクを確認できませんでした。"
        ),
        allow_failure=True,
    )

    if completed.returncode != 0:
        print(
            "KATANA Service auto-start task is not installed."
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
            project_directory=parsed.project_directory,
            task_command=parsed.task_command,
        )
        return 0

    if parsed.command == "remove":
        remove_task(
            task_name=parsed.task_name,
        )
        return 0

    if parsed.command == "migrate":
        migrate_task(
            project_directory=parsed.project_directory,
            task_command=parsed.task_command,
        )
        return 0

    show_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
