"""Sprint119D 全市場Universe自動パイプラインのテスト。"""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.market.market_calendar import TokyoMarketCalendar
from app.runtime.universe_daily_schedule_models import (
    UniverseDailyScheduleState,
)
from app.runtime.universe_daily_scheduler import (
    UniverseDailyScheduler,
)


NOW = datetime(
    2026,
    8,
    7,
    7,
    0,
    tzinfo=timezone.utc,
)


def test_bootstrap_continues_without_creating_marker(
    tmp_path: Path,
) -> None:
    bootstrap_report = tmp_path / "bootstrap.json"

    def runner(command, **_kwargs):
        assert "app.run_universe_bootstrap" in command
        bootstrap_report.write_text(
            json.dumps(
                {
                    "trading_date": "2026-08-07",
                    "universe_count": 3706,
                    "remaining_count": 3000,
                    "retryable_remaining_count": 3000,
                    "terminal_skipped_count": 0,
                    "coverage_ratio": 0.1905,
                    "completed": False,
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0)

    scheduler = UniverseDailyScheduler(
        enabled=True,
        database_path=tmp_path / "katana.db",
        report_path=bootstrap_report,
        primary_report_path=tmp_path / "primary.json",
        candidate_output_path=tmp_path / "candidates.txt",
        marker_directory=tmp_path / "markers",
        status_path=tmp_path / "status.json",
        calendar=TokyoMarketCalendar.with_custom_holidays([]),
        now_provider=lambda: NOW,
        command_runner=runner,
    )

    status = scheduler.run_once()

    assert status.state is UniverseDailyScheduleState.RUNNING
    assert status.requested_count == 3706
    assert not (
        tmp_path
        / "markers"
        / "2026-08-07.completed.json"
    ).exists()


def test_completed_bootstrap_runs_primary_screening(
    tmp_path: Path,
) -> None:
    bootstrap_report = tmp_path / "bootstrap.json"
    primary_report = tmp_path / "primary.json"
    candidates = tmp_path / "candidates.txt"
    calls = []

    def runner(command, **_kwargs):
        calls.append(command)

        if "app.run_universe_bootstrap" in command:
            bootstrap_report.write_text(
                json.dumps(
                    {
                        "trading_date": "2026-08-07",
                        "universe_count": 3706,
                        "remaining_count": 27,
                        "retryable_remaining_count": 0,
                        "terminal_skipped_count": 27,
                        "coverage_ratio": 1.0,
                        "completed": True,
                    }
                ),
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=0)

        assert "app.run_universe_primary_screening" in command
        primary_report.write_text(
            json.dumps(
                {
                    "evaluated_count": 3679,
                    "selected_count": 300,
                }
            ),
            encoding="utf-8",
        )
        candidates.write_text(
            "\n".join(
                f"{1000 + index}"
                for index in range(300)
            )
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0)

    scheduler = UniverseDailyScheduler(
        enabled=True,
        database_path=tmp_path / "katana.db",
        report_path=bootstrap_report,
        primary_report_path=primary_report,
        candidate_output_path=candidates,
        marker_directory=tmp_path / "markers",
        status_path=tmp_path / "status.json",
        calendar=TokyoMarketCalendar.with_custom_holidays([]),
        now_provider=lambda: NOW,
        command_runner=runner,
    )

    status = scheduler.run_once()

    assert status.state is UniverseDailyScheduleState.COMPLETED
    assert len(calls) == 2
    assert (
        tmp_path
        / "markers"
        / "2026-08-07.completed.json"
    ).exists()
