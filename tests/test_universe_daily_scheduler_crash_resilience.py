"""Sprint 134-1: Universe Daily Scheduler crash resilience."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.runtime.universe_daily_schedule_models import (
    UniverseDailyScheduleState,
)
from app.runtime.universe_daily_scheduler import UniverseDailyScheduler


TOKYO = ZoneInfo("Asia/Tokyo")


class _BusinessDayCalendar:
    def is_business_day(self, _date) -> bool:
        return True


def _scheduler(tmp_path: Path) -> UniverseDailyScheduler:
    return UniverseDailyScheduler(
        enabled=True,
        database_path=tmp_path / "katana.db",
        status_path=tmp_path / "status.json",
        report_path=tmp_path / "bootstrap.json",
        primary_report_path=tmp_path / "primary.json",
        candidate_output_path=tmp_path / "candidates.txt",
        unavailable_path=tmp_path / "unavailable.json",
        audit_report_path=tmp_path / "audit.json",
        crash_report_path=tmp_path / "crash.json",
        marker_directory=tmp_path / "markers",
        calendar=_BusinessDayCalendar(),
        now_provider=lambda: datetime(
            2026, 9, 7, 15, 40, tzinfo=TOKYO
        ),
        monotonic_provider=lambda: 100.0,
    )


def test_run_forever_survives_unexpected_cycle_exception(
    tmp_path: Path,
) -> None:
    scheduler = _scheduler(tmp_path)
    calls = {"count": 0}

    def run_once():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("simulated scheduler crash")
        scheduler.request_stop()

    scheduler.run_once = run_once  # type: ignore[method-assign]
    sleeps: list[float] = []

    scheduler.run_forever(
        poll_interval_seconds=0.01,
        sleep=sleeps.append,
    )

    assert calls["count"] == 2
    assert sleeps == [0.01]

    crash = json.loads(
        (tmp_path / "crash.json").read_text(encoding="utf-8")
    )
    assert crash["exception_type"] == "RuntimeError"
    assert crash["exception_message"] == "simulated scheduler crash"
    assert "RuntimeError: simulated scheduler crash" in crash["traceback"]

    status = json.loads(
        (tmp_path / "status.json").read_text(encoding="utf-8")
    )
    assert status["state"] == UniverseDailyScheduleState.FAILED.value
    assert "recovered from an unexpected cycle error" in status["message"]


def test_system_exit_is_not_swallowed(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path)

    def run_once():
        raise SystemExit(7)

    scheduler.run_once = run_once  # type: ignore[method-assign]

    try:
        scheduler.run_forever(
            poll_interval_seconds=0.01,
            sleep=lambda _seconds: None,
        )
    except SystemExit as error:
        assert error.code == 7
    else:
        raise AssertionError("SystemExit must escape run_forever")


def test_keyboard_interrupt_is_not_swallowed(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path)

    def run_once():
        raise KeyboardInterrupt()

    scheduler.run_once = run_once  # type: ignore[method-assign]

    try:
        scheduler.run_forever(
            poll_interval_seconds=0.01,
            sleep=lambda _seconds: None,
        )
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("KeyboardInterrupt must escape run_forever")
