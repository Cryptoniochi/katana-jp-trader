"""DynamicWatchlistSchedulerのテスト。"""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.market.market_calendar import TokyoMarketCalendar
from app.runtime.dynamic_watchlist_schedule_models import (
    DynamicWatchlistScheduleSettings,
    DynamicWatchlistScheduleState,
)
from app.runtime.dynamic_watchlist_scheduler import (
    DynamicWatchlistScheduler,
)


def build_scheduler(
    tmp_path: Path,
    *,
    command_runner,
    now: datetime,
) -> DynamicWatchlistScheduler:
    return DynamicWatchlistScheduler(
        enabled=True,
        database_path=tmp_path / "katana.db",
        watchlist_path=tmp_path / "watchlist.txt",
        report_directory=tmp_path / "reports",
        status_path=tmp_path / "schedule.json",
        latest_report_path=tmp_path / "reports" / "latest.json",
        marker_directory=tmp_path / "markers",
        settings=DynamicWatchlistScheduleSettings(
            minimum_symbols=5
        ),
        calendar=TokyoMarketCalendar.with_custom_holidays([]),
        now_provider=lambda: now,
        command_runner=command_runner,
    )


def test_closed_day_does_not_run(
    tmp_path: Path,
) -> None:
    commands = []
    scheduler = build_scheduler(
        tmp_path,
        command_runner=lambda *args, **kwargs: (
            commands.append((args, kwargs))
        ),
        now=datetime(
            2026, 8, 2, 0, 0,
            tzinfo=timezone.utc,
        ),
    )

    status = scheduler.run_once()

    assert status.state is DynamicWatchlistScheduleState.CLOSED_DAY
    assert commands == []


def test_successful_update_creates_marker(
    tmp_path: Path,
) -> None:
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        report = tmp_path / "reports" / "latest.json"
        report.parent.mkdir(parents=True)
        report.write_text(
            json.dumps(
                {
                    "applied": True,
                    "selected": [
                        {"code": str(1000 + index)}
                        for index in range(5)
                    ],
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0)

    scheduler = build_scheduler(
        tmp_path,
        command_runner=run,
        now=datetime(
            2026, 8, 3, 0, 0,
            tzinfo=timezone.utc,
        ),
    )

    status = scheduler.run_once()

    assert status.state is DynamicWatchlistScheduleState.COMPLETED
    assert status.selected_count == 5
    assert status.applied is True
    assert len(commands) == 1
    assert "--apply" in commands[0]
    assert (
        tmp_path
        / "markers"
        / "2026-08-03.applied.json"
    ).exists()


def test_failed_update_does_not_create_marker(
    tmp_path: Path,
) -> None:
    scheduler = build_scheduler(
        tmp_path,
        command_runner=lambda *_args, **_kwargs: (
            SimpleNamespace(returncode=1)
        ),
        now=datetime(
            2026, 8, 3, 0, 0,
            tzinfo=timezone.utc,
        ),
    )

    status = scheduler.run_once()

    assert status.state is DynamicWatchlistScheduleState.FAILED
    assert not (
        tmp_path
        / "markers"
        / "2026-08-03.applied.json"
    ).exists()
