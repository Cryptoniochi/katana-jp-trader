"""ScheduledPaperTradingControllerのテスト。"""

from datetime import datetime, timezone
from pathlib import Path

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


def test_disabled_controller_never_starts(
    tmp_path: Path,
) -> None:
    started = []

    controller = ScheduledPaperTradingController(
        enabled=False,
        status_path=tmp_path / "status.json",
        now_provider=lambda: datetime(
            2026,
            8,
            3,
            9,
            0,
            tzinfo=timezone.utc,
        ),
        popen_factory=lambda *args, **kwargs: (
            started.append((args, kwargs))
        ),
    )

    status = controller.run_once()

    assert status.state is ScheduledTradingState.DISABLED
    assert started == []


def test_business_day_starts_market_session(
    tmp_path: Path,
) -> None:
    process = FakeProcess()

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
        readiness_check_enabled=False,
    )

    status = controller.run_once()

    assert status.state is ScheduledTradingState.RUNNING
    assert status.process_id == 4321


def test_weekend_is_closed_day(
    tmp_path: Path,
) -> None:
    controller = ScheduledPaperTradingController(
        enabled=True,
        calendar=TokyoMarketCalendar.with_custom_holidays(
            []
        ),
        status_path=tmp_path / "status.json",
        now_provider=lambda: datetime(
            2026,
            8,
            2,
            0,
            0,
            tzinfo=timezone.utc,
        ),
    )

    status = controller.run_once()

    assert status.state is ScheduledTradingState.CLOSED_DAY
