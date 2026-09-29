"""Scheduled Paper Tradingの事前確認テスト。"""

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


def test_failed_preflight_does_not_start_market_session(
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

    controller = ScheduledPaperTradingController(
        enabled=True,
        calendar=TokyoMarketCalendar.with_custom_holidays(
            []
        ),
        status_path=tmp_path / "status.json",
        now_provider=lambda: datetime(
            2026,
            8,
            3,
            0,
            0,
            tzinfo=timezone.utc,
        ),
        popen_factory=lambda *args, **kwargs: (
            started.append((args, kwargs))
        ),
    )

    status = controller.run_once()

    assert status.state is ScheduledTradingState.FAILED
    assert started == []


def test_successful_preflight_starts_market_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    process = FakeProcess()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0
        ),
    )

    controller = ScheduledPaperTradingController(
        enabled=True,
        calendar=TokyoMarketCalendar.with_custom_holidays(
            []
        ),
        status_path=tmp_path / "status.json",
        now_provider=lambda: datetime(
            2026,
            8,
            3,
            0,
            0,
            tzinfo=timezone.utc,
        ),
        popen_factory=lambda *_args, **_kwargs: process,
    )

    status = controller.run_once()

    assert status.state is ScheduledTradingState.RUNNING
    assert status.process_id == 4321


def test_preflight_uses_same_paper_runtime_arguments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        module.subprocess,
        "run",
        fake_run,
    )
    controller = ScheduledPaperTradingController(
        enabled=True,
        calendar=TokyoMarketCalendar.with_custom_holidays(
            []
        ),
        status_path=tmp_path / "status.json",
        paper_arguments=(
            "--database-path",
            "data/katana.db",
            "--enable-shadow-replication",
        ),
        now_provider=lambda: datetime(
            2026,
            8,
            3,
            0,
            0,
            tzinfo=timezone.utc,
        ),
        popen_factory=lambda *_args, **_kwargs: FakeProcess(),
    )

    controller.run_once()

    readiness = next(
        command
        for command in commands
        if "app.run_paper_trading" in command
    )
    assert "--enable-shadow-replication" in readiness
    assert "--check" in readiness
