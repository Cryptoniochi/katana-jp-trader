"""Project KATANAをWindows Task Schedulerへ登録する。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from typing import TextIO

from app.scheduler_task import (
    DEFAULT_START_TIME,
    DEFAULT_TASK_NAME,
    SchedulerTaskSettings,
    default_scheduler_task_settings,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """タスク登録CLI引数を定義する。"""

    parser = argparse.ArgumentParser(
        prog="python -m app.install_scheduler",
        description=(
            "Project KATANAの自動運用タスクを"
            "Windows Task Schedulerへ登録します。"
        ),
    )
    parser.add_argument(
        "--task-name",
        default=DEFAULT_TASK_NAME,
        help="Windowsタスク名",
    )
    parser.add_argument(
        "--start-time",
        default=DEFAULT_START_TIME,
        help="平日の開始時刻（HH:MM）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="同名タスクを上書きします。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="登録せず実行内容だけ表示します。",
    )

    return parser


def _ps_quote(value: str) -> str:
    """PowerShellの単一引用符文字列へ変換する。"""

    return "'" + value.replace("'", "''") + "'"


def build_create_command(
    settings: SchedulerTaskSettings,
    *,
    force: bool,
) -> list[str]:
    """ScheduledTasks PowerShellコマンドを生成する。"""

    days = ",".join(
        _ps_quote(day)
        for day in settings.weekdays
    )
    force_switch = " -Force" if force else ""

    script = (
        "$ErrorActionPreference='Stop';"
        "$action=New-ScheduledTaskAction "
        f"-Execute {_ps_quote(str(settings.python_executable))} "
        f"-Argument {_ps_quote(settings.action_arguments)} "
        f"-WorkingDirectory {_ps_quote(str(settings.project_root))};"
        "$trigger=New-ScheduledTaskTrigger "
        "-Weekly "
        f"-DaysOfWeek {days} "
        f"-At {_ps_quote(settings.start_time)};"
        "$taskSettings=New-ScheduledTaskSettingsSet "
        "-StartWhenAvailable "
        "-WakeToRun "
        "-MultipleInstances IgnoreNew "
        "-RestartCount 3 "
        "-RestartInterval (New-TimeSpan -Minutes 5);"
        "Register-ScheduledTask "
        f"-TaskName {_ps_quote(settings.task_name)} "
        "-Action $action "
        "-Trigger $trigger "
        "-Settings $taskSettings "
        "-Description "
        + _ps_quote(
            "Project KATANA automated paper trading"
        )
        + force_switch
        + " | Out-Null;"
        "Write-Output 'SUCCESS'"
    )

    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]


def run(
    argv: Sequence[str] | None = None,
    *,
    output: TextIO = sys.stdout,
    error_output: TextIO = sys.stderr,
    command_runner=subprocess.run,
    settings_factory=default_scheduler_task_settings,
) -> int:
    """Windowsタスクを登録して終了コードを返す。"""

    if sys.platform != "win32":
        print(
            "Windowsでのみ実行できます。",
            file=error_output,
        )
        return 1

    arguments = build_argument_parser().parse_args(argv)

    try:
        settings = settings_factory(
            task_name=arguments.task_name,
            start_time=arguments.start_time,
        )
        command = build_create_command(
            settings,
            force=arguments.force,
        )

        print(
            f"task_name={settings.task_name}",
            file=output,
        )
        print(
            f"start_time={settings.start_time}",
            file=output,
        )
        print(
            f"weekdays={','.join(settings.weekdays)}",
            file=output,
        )
        print(
            f"python={settings.python_executable}",
            file=output,
        )
        print(
            f"project_root={settings.project_root}",
            file=output,
        )
        print(
            f"arguments={settings.action_arguments}",
            file=output,
        )
        print(
            "restart=5分間隔で最大3回",
            file=output,
        )
        print(
            "multiple_instances=IgnoreNew",
            file=output,
        )

        if arguments.dry_run:
            print(
                "dry_run=True",
                file=output,
            )
            return 0

        completed = command_runner(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if completed.stdout.strip():
            print(
                completed.stdout.strip(),
                file=output,
            )

        if completed.returncode != 0:
            detail = (
                completed.stderr.strip()
                or "ScheduledTasks registration failed"
            )
            print(
                "タスク登録に失敗しました。 "
                f"error={detail}",
                file=error_output,
            )
            return int(completed.returncode or 1)

        print(
            "Project KATANAの自動運用タスクを"
            "登録しました。",
            file=output,
        )
        return 0

    except Exception as error:
        print(
            "タスク登録を実行できませんでした。 "
            f"error={error}",
            file=error_output,
        )
        return 1


def main() -> None:
    """CLIエントリーポイント。"""

    raise SystemExit(
        run(sys.argv[1:])
    )


if __name__ == "__main__":
    main()
