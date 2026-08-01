"""Service ManagerのDaily Report Scheduler統合テスト。"""

from pathlib import Path

from app.runtime.katana_service_manager import (
    build_daily_report_scheduler_command,
)


def test_daily_report_scheduler_command_is_enabled_explicitly() -> None:
    command = build_daily_report_scheduler_command(
        database_path=Path("data/katana.db"),
        enabled=True,
    )

    assert "app.run_daily_report_scheduler" in command
    assert "--enable" in command

    database_index = command.index(
        "--database-path"
    )
    database_argument = command[
        database_index + 1
    ]

    assert Path(database_argument) == Path(
        "data/katana.db"
    )


def test_daily_report_scheduler_command_can_remain_disabled() -> None:
    command = build_daily_report_scheduler_command(
        database_path=Path("data/katana.db"),
        enabled=False,
    )

    assert "--enable" not in command
