"""DailyReportSchedulerのテスト。"""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.market.market_calendar import TokyoMarketCalendar
from app.runtime.daily_report_scheduler import (
    DailyReportScheduler,
)
from app.runtime.daily_report_schedule_models import (
    DailyReportScheduleState,
)


def test_disabled_scheduler_does_not_run_commands(
    tmp_path: Path,
) -> None:
    commands = []
    scheduler = DailyReportScheduler(
        enabled=False,
        database_path=tmp_path / "katana.db",
        status_path=tmp_path / "status.json",
        marker_directory=tmp_path / "markers",
        now_provider=lambda: datetime(
            2026,
            8,
            3,
            7,
            0,
            tzinfo=timezone.utc,
        ),
        command_runner=lambda *args, **kwargs: (
            commands.append((args, kwargs))
        ),
    )

    status = scheduler.run_once()

    assert status.state is DailyReportScheduleState.DISABLED
    assert commands == []


def test_business_day_after_schedule_runs_report_and_notification(
    tmp_path: Path,
) -> None:
    commands = []

    def command_runner(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)

    scheduler = DailyReportScheduler(
        enabled=True,
        database_path=tmp_path / "katana.db",
        report_directory=tmp_path / "daily",
        status_path=tmp_path / "status.json",
        marker_directory=tmp_path / "markers",
        calendar=TokyoMarketCalendar.with_custom_holidays(
            []
        ),
        now_provider=lambda: datetime(
            2026,
            8,
            3,
            7,
            0,
            tzinfo=timezone.utc,
        ),
        command_runner=command_runner,
    )

    status = scheduler.run_once()

    assert status.state is DailyReportScheduleState.COMPLETED
    assert len(commands) == 2
    assert "app.run_daily_report" in commands[0]
    assert "app.run_daily_report_notification" in commands[1]
    assert (
        tmp_path
        / "markers"
        / "2026-08-03.sent.json"
    ).exists()


def test_marker_prevents_duplicate_notification(
    tmp_path: Path,
) -> None:
    marker = (
        tmp_path
        / "markers"
        / "2026-08-03.sent.json"
    )
    marker.parent.mkdir(parents=True)
    marker.write_text("{}", encoding="utf-8")
    commands = []

    scheduler = DailyReportScheduler(
        enabled=True,
        database_path=tmp_path / "katana.db",
        status_path=tmp_path / "status.json",
        marker_directory=tmp_path / "markers",
        calendar=TokyoMarketCalendar.with_custom_holidays(
            []
        ),
        now_provider=lambda: datetime(
            2026,
            8,
            3,
            7,
            0,
            tzinfo=timezone.utc,
        ),
        command_runner=lambda *args, **kwargs: (
            commands.append((args, kwargs))
        ),
    )

    status = scheduler.run_once()

    assert status.state is DailyReportScheduleState.COMPLETED
    assert commands == []
