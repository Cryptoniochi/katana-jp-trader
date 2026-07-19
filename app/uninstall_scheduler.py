"""Project KATANAのWindowsタスクを削除する。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from typing import TextIO

from app.scheduler_task import DEFAULT_TASK_NAME


def build_argument_parser() -> argparse.ArgumentParser:
    """タスク削除CLI引数を定義する。"""

    parser = argparse.ArgumentParser(
        prog="python -m app.uninstall_scheduler",
        description=(
            "Project KATANAの自動運用タスクを"
            "Windows Task Schedulerから削除します。"
        ),
    )
    parser.add_argument(
        "--task-name",
        default=DEFAULT_TASK_NAME,
        help="削除するWindowsタスク名",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="削除せず対象だけ表示します。",
    )

    return parser


def build_delete_command(
    task_name: str,
) -> list[str]:
    """schtasks.exeの削除コマンドを生成する。"""

    normalized = task_name.strip()

    if not normalized:
        raise ValueError(
            "タスク名を指定してください。"
        )

    return [
        "schtasks.exe",
        "/Delete",
        "/TN",
        normalized,
        "/F",
    ]


def run(
    argv: Sequence[str] | None = None,
    *,
    output: TextIO = sys.stdout,
    error_output: TextIO = sys.stderr,
    command_runner=subprocess.run,
) -> int:
    """Windowsタスクを削除して終了コードを返す。"""

    if sys.platform != "win32":
        print(
            "Windowsでのみ実行できます。",
            file=error_output,
        )
        return 1

    arguments = build_argument_parser().parse_args(argv)

    try:
        command = build_delete_command(
            arguments.task_name
        )

        print(
            f"task_name={arguments.task_name}",
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
                or "schtasks.exe failed"
            )
            print(
                "タスク削除に失敗しました。 "
                f"error={detail}",
                file=error_output,
            )
            return int(completed.returncode or 1)

        print(
            "Project KATANAの自動運用タスクを"
            "削除しました。",
            file=output,
        )
        return 0

    except Exception as error:
        print(
            "タスク削除を実行できませんでした。 "
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
