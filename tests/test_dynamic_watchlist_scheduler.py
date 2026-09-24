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
    candidate_path = tmp_path / "universe_candidates.txt"
    candidate_path.write_text(
        "7203\n6758\n9984\n8306\n9432\n",
        encoding="utf-8",
    )
    return DynamicWatchlistScheduler(
        enabled=True,
        database_path=tmp_path / "katana.db",
        watchlist_path=tmp_path / "watchlist.txt",
        report_directory=tmp_path / "reports",
        status_path=tmp_path / "schedule.json",
        latest_report_path=tmp_path / "reports" / "latest.json",
        marker_directory=tmp_path / "markers",
        candidate_universe_path=candidate_path,
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
                    "target_date": "2026-08-03",
                    "market_data_date": "2026-07-31",
                    "market_data_age_days": 3,
                    "latest_market_bar_count": 5,
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


def test_cold_start_retains_existing_valid_watchlist(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    import sqlite3

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE market_bars (
                code TEXT NOT NULL,
                traded_at TEXT NOT NULL,
                interval_minutes INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER NOT NULL,
                data_source TEXT NOT NULL
            )
            """
        )

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
    scheduler.watchlist_path.write_text(
        "7203\n6758\n9984\n8306\n9432\n",
        encoding="utf-8",
    )

    status = scheduler.run_once()

    assert status.state is DynamicWatchlistScheduleState.COMPLETED
    assert status.selected_count == 5
    assert status.applied is True
    assert status.last_exit_code == 0
    payload = json.loads(
        scheduler.latest_report_path.read_text(encoding="utf-8")
    )
    assert payload["cold_start_fallback"] is True
    assert [item["code"] for item in payload["selected"]] == [
        "7203",
        "6758",
        "9984",
        "8306",
        "9432",
    ]
    marker = json.loads(
        (
            tmp_path / "markers" / "2026-08-03.applied.json"
        ).read_text(encoding="utf-8")
    )
    assert marker["mature_history_count"] == 0


def test_cold_start_does_not_hide_failure_when_history_is_mature(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    import sqlite3

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE market_bars (
                code TEXT NOT NULL,
                traded_at TEXT NOT NULL,
                interval_minutes INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER NOT NULL,
                data_source TEXT NOT NULL
            )
            """
        )
        for code in ("7203", "6758", "9984", "8306", "9432"):
            for day in ("01", "02", "03"):
                connection.execute(
                    """
                    INSERT INTO market_bars VALUES (
                        ?, ?, 1440, 100, 110, 90, 105, 10000, 'test'
                    )
                    """,
                    (code, f"2026-08-{day}T00:00:00+00:00"),
                )

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
    scheduler.watchlist_path.write_text(
        "7203\n6758\n9984\n8306\n9432\n",
        encoding="utf-8",
    )

    status = scheduler.run_once()

    assert status.state is DynamicWatchlistScheduleState.FAILED
    assert not scheduler.latest_report_path.exists()
