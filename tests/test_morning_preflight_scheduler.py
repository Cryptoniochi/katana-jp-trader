"""MorningPreflightSchedulerのテスト。"""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.market.market_calendar import TokyoMarketCalendar
from app.runtime.morning_preflight_scheduler import (
    MorningPreflightScheduler,
)
from app.runtime.morning_preflight_schedule_models import (
    MorningPreflightScheduleState,
)


def test_closed_day_does_not_send(
    tmp_path: Path,
) -> None:
    commands = []
    scheduler = MorningPreflightScheduler(
        enabled=True,
        status_path=tmp_path / "status.json",
        marker_directory=tmp_path / "markers",
        calendar=TokyoMarketCalendar.with_custom_holidays(
            []
        ),
        now_provider=lambda: datetime(
            2026,
            8,
            2,
            0,
            0,
            tzinfo=timezone.utc,
        ),
        command_runner=lambda *args, **kwargs: (
            commands.append((args, kwargs))
        ),
    )

    status = scheduler.run_once()

    assert status.state is MorningPreflightScheduleState.CLOSED_DAY
    assert commands == []


def test_business_day_after_0840_sends_once(
    tmp_path: Path,
) -> None:
    commands = []

    def command_runner(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)

    scheduler = MorningPreflightScheduler(
        enabled=True,
        status_path=tmp_path / "status.json",
        marker_directory=tmp_path / "markers",
        calendar=TokyoMarketCalendar.with_custom_holidays(
            []
        ),
        now_provider=lambda: datetime(
            2026,
            8,
            3,
            0,
            0,
            tzinfo=timezone.utc,
        ),
        command_runner=command_runner,
    )

    status = scheduler.run_once()

    assert status.state is MorningPreflightScheduleState.COMPLETED
    assert len(commands) == 1
    assert "app.run_morning_preflight" in commands[0]
    assert (
        tmp_path
        / "markers"
        / "2026-08-03.sent.json"
    ).exists()


def test_marker_prevents_duplicate_send(
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

    scheduler = MorningPreflightScheduler(
        enabled=True,
        status_path=tmp_path / "status.json",
        marker_directory=tmp_path / "markers",
        calendar=TokyoMarketCalendar.with_custom_holidays(
            []
        ),
        now_provider=lambda: datetime(
            2026,
            8,
            3,
            0,
            0,
            tzinfo=timezone.utc,
        ),
        command_runner=lambda *args, **kwargs: (
            commands.append((args, kwargs))
        ),
    )

    status = scheduler.run_once()

    assert status.state is MorningPreflightScheduleState.COMPLETED
    assert commands == []
