"""市場終了時のScheduler終了シーケンスを検証する。"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.runtime.scheduled_paper_trading import (
    ScheduledPaperTradingController,
)
from app.runtime.scheduled_paper_trading_models import (
    ScheduledTradingState,
)


TOKYO = ZoneInfo("Asia/Tokyo")


class BusinessDayCalendar:
    def is_business_day(self, _date) -> bool:
        return True


class RunningProcess:
    pid = 1234
    returncode = None

    def poll(self):
        return None

    def terminate(self):
        raise AssertionError(
            "15:30時点でterminateしてはいけません。"
        )


class CompletedProcess:
    pid = 1234
    returncode = 0

    def poll(self):
        return 0


def build_controller(
    *,
    now: datetime,
    status_path: Path,
) -> ScheduledPaperTradingController:
    return ScheduledPaperTradingController(
        enabled=True,
        calendar=BusinessDayCalendar(),
        status_path=status_path,
        readiness_check_enabled=False,
        autonomous_guard_enabled=False,
        now_provider=lambda: now,
    )


def test_market_close_waits_for_graceful_shutdown(
    tmp_path: Path,
) -> None:
    controller = build_controller(
        now=datetime(
            2026, 8, 5, 15, 30, 10,
            tzinfo=TOKYO,
        ),
        status_path=tmp_path / "status.json",
    )
    controller.process = RunningProcess()

    status = controller.run_once()

    assert status.state is ScheduledTradingState.STOPPING
    assert status.process_id == 1234
    assert status.next_action_at is not None
    assert status.next_action_at.hour == 15
    assert status.next_action_at.minute == 35


def test_normal_child_exit_marks_completed(
    tmp_path: Path,
) -> None:
    controller = build_controller(
        now=datetime(
            2026, 8, 5, 15, 31,
            tzinfo=TOKYO,
        ),
        status_path=tmp_path / "status.json",
    )
    controller.process = CompletedProcess()

    status = controller.run_once()

    assert status.state is ScheduledTradingState.COMPLETED
    assert status.process_id is None
    assert status.last_exit_code == 0


def test_before_market_close_keeps_running(
    tmp_path: Path,
) -> None:
    controller = build_controller(
        now=datetime(
            2026, 8, 5, 15, 29,
            tzinfo=TOKYO,
        ),
        status_path=tmp_path / "status.json",
    )
    controller.process = RunningProcess()

    status = controller.run_once()

    assert status.state is ScheduledTradingState.RUNNING
