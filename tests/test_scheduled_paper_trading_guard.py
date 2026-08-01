"""Scheduled Paper Tradingの自律運転Guardテスト。"""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import app.runtime.scheduled_paper_trading as module
from app.market.market_calendar import TokyoMarketCalendar
from app.runtime.scheduled_paper_trading import (
    ScheduledPaperTradingController,
)
from app.runtime.scheduled_paper_trading_models import (
    ScheduledTradingState,
)


class FakeProcess:
    pid = 4321
    returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


def build_controller(
    tmp_path: Path,
    *,
    popen_factory,
) -> ScheduledPaperTradingController:
    return ScheduledPaperTradingController(
        enabled=True,
        calendar=TokyoMarketCalendar.with_custom_holidays(
            []
        ),
        status_path=tmp_path / "schedule.json",
        autonomous_guard_report_path=(
            tmp_path / "autonomous.json"
        ),
        now_provider=lambda: datetime(
            2026,
            8,
            3,
            0,
            0,
            tzinfo=timezone.utc,
        ),
        popen_factory=popen_factory,
        readiness_check_enabled=False,
    )


def test_failed_guard_blocks_market_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    started = []
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1
        ),
    )

    status = build_controller(
        tmp_path,
        popen_factory=lambda *args, **kwargs: (
            started.append((args, kwargs))
        ),
    ).run_once()

    assert status.state is ScheduledTradingState.FAILED
    assert started == []
    assert "Guard blocked" in status.message


def test_successful_guard_allows_market_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    process = FakeProcess()
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        module.subprocess,
        "run",
        fake_run,
    )

    status = build_controller(
        tmp_path,
        popen_factory=lambda *_args, **_kwargs: process,
    ).run_once()

    assert status.state is ScheduledTradingState.RUNNING
    assert status.process_id == 4321
    assert any(
        "app.run_autonomous_operation_validation"
        in command
        for command in commands
    )


def test_guard_can_be_disabled_for_isolated_tests(
    tmp_path: Path,
) -> None:
    process = FakeProcess()

    controller = ScheduledPaperTradingController(
        enabled=True,
        calendar=TokyoMarketCalendar.with_custom_holidays(
            []
        ),
        status_path=tmp_path / "schedule.json",
        now_provider=lambda: datetime(
            2026,
            8,
            3,
            0,
            0,
            tzinfo=timezone.utc,
        ),
        popen_factory=lambda *_args, **_kwargs: process,
        autonomous_guard_enabled=False,
        readiness_check_enabled=False,
    )

    status = controller.run_once()

    assert status.state is ScheduledTradingState.RUNNING
