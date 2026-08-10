"""Sprint 124: SchedulerのDaily History Audit統合テスト。"""

import json
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.market.market_calendar import TokyoMarketCalendar
from app.runtime.universe_daily_history_audit_service import (
    UniverseDailyHistoryAuditResult,
)
from app.runtime.universe_daily_schedule_models import (
    UniverseDailyScheduleState,
)
from app.runtime.universe_daily_scheduler import UniverseDailyScheduler


NOW = datetime(2026, 8, 10, 7, 0, tzinfo=timezone.utc)
DAY = date(2026, 8, 10)


class FakeAuditService:
    def __init__(self, *, completed: bool) -> None:
        self.completed = completed
        self.calls = []

    def audit(self, *, trading_date: date):
        self.calls.append(trading_date)
        unexplained = 0 if self.completed else 1
        collected = 3679 if self.completed else 3678
        effective = 1.0 if self.completed else 0.99973
        return UniverseDailyHistoryAuditResult(
            generated_at=NOW,
            trading_date=trading_date,
            active_universe_count=3706,
            collected_count=collected,
            missing_count=3706 - collected,
            terminal_skipped_count=27,
            unexplained_missing_count=unexplained,
            collection_ratio=collected / 3706,
            effective_coverage_ratio=effective,
            completed=self.completed,
            symbols_with_1_day=3679,
            symbols_with_5_days=6,
            symbols_with_10_days=1,
            symbols_with_20_days=0,
            fallback_count=3678,
            developing_count=1,
            strict_count=0,
            missing_codes=("1795",),
            unexplained_missing_codes=(
                () if self.completed else ("9999",)
            ),
        )


def _scheduler(
    tmp_path: Path,
    *,
    audit_completed: bool,
):
    report = tmp_path / "bootstrap.json"
    primary = tmp_path / "primary.json"
    candidates = tmp_path / "candidates.txt"
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        module = command[2]
        if module == "app.run_universe_bootstrap":
            report.write_text(
                json.dumps(
                    {
                        "trading_date": "2026-08-10",
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

        if module == "app.run_universe_primary_screening":
            primary.write_text(
                json.dumps(
                    {
                        "evaluated_count": 300,
                        "selected_count": 5,
                    }
                ),
                encoding="utf-8",
            )
            candidates.write_text(
                "1001\n1002\n1003\n1004\n1005\n",
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=0)

        raise AssertionError(module)

    audit = FakeAuditService(completed=audit_completed)
    scheduler = UniverseDailyScheduler(
        enabled=True,
        database_path=tmp_path / "katana.db",
        report_path=report,
        primary_report_path=primary,
        candidate_output_path=candidates,
        unavailable_path=tmp_path / "unavailable.json",
        audit_report_path=tmp_path / "audit.json",
        status_path=tmp_path / "status.json",
        marker_directory=tmp_path / "markers",
        calendar=TokyoMarketCalendar.with_custom_holidays([]),
        now_provider=lambda: NOW,
        command_runner=run,
        history_audit_service=audit,
    )
    return scheduler, audit, commands


def test_audit_passes_before_primary_screening(
    tmp_path: Path,
) -> None:
    scheduler, audit, commands = _scheduler(
        tmp_path,
        audit_completed=True,
    )

    status = scheduler.run_once()

    assert status.state is UniverseDailyScheduleState.COMPLETED
    assert audit.calls == [DAY]
    assert [command[2] for command in commands] == [
        "app.run_universe_bootstrap",
        "app.run_universe_primary_screening",
    ]

    marker = json.loads(
        (
            tmp_path
            / "markers"
            / "2026-08-10.completed.json"
        ).read_text(encoding="utf-8")
    )
    assert marker["audit_completed"] is True
    assert marker["effective_coverage_ratio"] == 1.0
    assert marker["primary_selected_count"] == 5
    assert (tmp_path / "audit.json").exists()


def test_failed_audit_blocks_primary_screening_and_marker(
    tmp_path: Path,
) -> None:
    scheduler, audit, commands = _scheduler(
        tmp_path,
        audit_completed=False,
    )

    status = scheduler.run_once()

    assert status.state is UniverseDailyScheduleState.FAILED
    assert audit.calls == [DAY]
    assert [command[2] for command in commands] == [
        "app.run_universe_bootstrap"
    ]
    assert not (
        tmp_path
        / "markers"
        / "2026-08-10.completed.json"
    ).exists()
    assert "Daily History Audit failed" in status.message
