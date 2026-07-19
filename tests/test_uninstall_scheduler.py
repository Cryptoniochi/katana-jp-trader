"""Windowsタスク削除CLIのテスト。"""

from io import StringIO
from types import SimpleNamespace

from app.uninstall_scheduler import (
    build_delete_command,
    run,
)


def test_delete_command() -> None:
    assert build_delete_command(
        "Project KATANA"
    ) == [
        "schtasks.exe",
        "/Delete",
        "/TN",
        "Project KATANA",
        "/F",
    ]


def test_successful_uninstall(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.uninstall_scheduler.sys.platform",
        "win32",
    )

    exit_code = run(
        [],
        output=StringIO(),
        error_output=StringIO(),
        command_runner=(
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0,
                stdout="SUCCESS",
                stderr="",
            )
        ),
    )

    assert exit_code == 0
