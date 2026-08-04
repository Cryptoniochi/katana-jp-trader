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



class MutableClock:
    def __init__(
        self,
        value: datetime,
    ) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def test_market_close_stops_process_and_completes(
    tmp_path: Path,
) -> None:
    process = FakeProcess()
    clock = MutableClock(
        datetime(
            2026, 8, 3, 5, 29,
            tzinfo=timezone.utc,
        )
    )
    started = []

    def popen_factory(*_args, **_kwargs):
        started.append(process)
        return process

    controller = ScheduledPaperTradingController(
        enabled=True,
        calendar=TokyoMarketCalendar.with_custom_holidays(
            []
        ),
        status_path=tmp_path / "status.json",
        now_provider=clock,
        popen_factory=popen_factory,
        readiness_check_enabled=False,
        autonomous_guard_enabled=False,
    )

    running = controller.run_once()
    assert running.state is ScheduledTradingState.RUNNING
    assert running.process_id == 4321
    assert len(started) == 1

    clock.value = datetime(
        2026, 8, 3, 6, 30,
        tzinfo=timezone.utc,
    )
    completed = controller.run_once()

    assert completed.state is ScheduledTradingState.COMPLETED
    assert completed.process_id is None
    assert process.returncode == 0
    assert len(started) == 1


def test_market_close_does_not_restart_same_day(
    tmp_path: Path,
) -> None:
    clock = MutableClock(
        datetime(
            2026, 8, 3, 6, 30,
            tzinfo=timezone.utc,
        )
    )
    started = []

    controller = ScheduledPaperTradingController(
        enabled=True,
        calendar=TokyoMarketCalendar.with_custom_holidays(
            []
        ),
        status_path=tmp_path / "status.json",
        now_provider=clock,
        popen_factory=lambda *_args, **_kwargs: (
            started.append(FakeProcess())
            or started[-1]
        ),
        readiness_check_enabled=False,
        autonomous_guard_enabled=False,
    )

    first = controller.run_once()
    second = controller.run_once()

    assert first.state is ScheduledTradingState.COMPLETED
    assert second.state is ScheduledTradingState.COMPLETED
    assert started == []


def test_new_business_day_can_start_again(
    tmp_path: Path,
) -> None:
    clock = MutableClock(
        datetime(
            2026, 8, 3, 6, 30,
            tzinfo=timezone.utc,
        )
    )
    started = []

    controller = ScheduledPaperTradingController(
        enabled=True,
        calendar=TokyoMarketCalendar.with_custom_holidays(
            []
        ),
        status_path=tmp_path / "status.json",
        now_provider=clock,
        popen_factory=lambda *_args, **_kwargs: (
            started.append(FakeProcess())
            or started[-1]
        ),
        readiness_check_enabled=False,
        autonomous_guard_enabled=False,
    )

    completed = controller.run_once()
    assert completed.state is ScheduledTradingState.COMPLETED

    clock.value = datetime(
        2026, 8, 4, 0, 0,
        tzinfo=timezone.utc,
    )
    running = controller.run_once()

    assert running.state is ScheduledTradingState.RUNNING
    assert len(started) == 1
