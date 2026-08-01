"""営業日と時刻に応じてPaper Tradingを安全に制御する。"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from datetime import datetime, time as clock_time
from pathlib import Path
from zoneinfo import ZoneInfo

from app.market.market_calendar import TokyoMarketCalendar
from app.runtime.scheduled_paper_trading_models import (
    ScheduledTradingState,
    ScheduledTradingStatus,
    TradingScheduleSettings,
)


TOKYO = ZoneInfo("Asia/Tokyo")
DEFAULT_STATUS_PATH = Path(
    "reports/service/paper_trading_schedule.json"
)


class ScheduledPaperTradingController:
    """既存run_market_sessionを子プロセスとして管理する。"""

    def __init__(
        self,
        *,
        enabled: bool,
        settings: TradingScheduleSettings | None = None,
        calendar: TokyoMarketCalendar | None = None,
        status_path: Path = DEFAULT_STATUS_PATH,
        paper_arguments: Sequence[str] = (),
        readiness_check_enabled: bool = True,
        readiness_timeout_seconds: float = 30.0,
        autonomous_guard_enabled: bool = True,
        autonomous_guard_timeout_seconds: float = 120.0,
        autonomous_guard_report_path: Path = Path(
            "reports/service/autonomous_operation_report.json"
        ),
        now_provider: Callable[[], datetime] | None = None,
        popen_factory: Callable[..., subprocess.Popen] = (
            subprocess.Popen
        ),
        monotonic_provider: Callable[[], float] = (
            time.monotonic
        ),
    ) -> None:
        self.enabled = enabled
        self.settings = (
            settings
            if settings is not None
            else TradingScheduleSettings()
        )
        self.calendar = (
            calendar
            if calendar is not None
            else TokyoMarketCalendar()
        )
        self.status_path = Path(status_path)
        self.paper_arguments = tuple(
            paper_arguments
        )
        self.readiness_check_enabled = (
            readiness_check_enabled
        )
        self.readiness_timeout_seconds = (
            readiness_timeout_seconds
        )
        self.autonomous_guard_enabled = (
            autonomous_guard_enabled
        )
        self.autonomous_guard_timeout_seconds = (
            autonomous_guard_timeout_seconds
        )
        self.autonomous_guard_report_path = Path(
            autonomous_guard_report_path
        )

        if self.readiness_timeout_seconds <= 0:
            raise ValueError(
                "Readinessタイムアウトは0より大きい必要があります。"
            )

        if self.autonomous_guard_timeout_seconds <= 0:
            raise ValueError(
                "自律運転Guardタイムアウトは"
                "0より大きい必要があります。"
            )
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(TOKYO)
        )
        self.popen_factory = popen_factory
        self.monotonic_provider = (
            monotonic_provider
        )
        self.process: subprocess.Popen | None = None
        self.last_exit_code: int | None = None
        self._stop_requested = False

    def run_once(self) -> ScheduledTradingStatus:
        """現在時刻に必要な開始・停止処理を1回行う。"""

        now = self._current_time()
        business_day = self.calendar.is_business_day(
            now.date()
        )

        if not self.enabled:
            return self._publish(
                now=now,
                state=ScheduledTradingState.DISABLED,
                business_day=business_day,
                next_action_at=None,
                message=(
                    "Scheduled Paper Trading is disabled."
                ),
            )

        if not business_day:
            self._stop_process()
            return self._publish(
                now=now,
                state=ScheduledTradingState.CLOSED_DAY,
                business_day=False,
                next_action_at=None,
                message=(
                    "Tokyo market is closed today."
                ),
            )

        local_time = now.timetz().replace(
            tzinfo=None
        )

        if local_time < self.settings.start_at:
            return self._publish(
                now=now,
                state=ScheduledTradingState.BEFORE_START,
                business_day=True,
                next_action_at=self._at(
                    now,
                    self.settings.start_at,
                ),
                message=(
                    "Waiting for scheduled startup."
                ),
            )

        if local_time >= self.settings.stop_at:
            self._stop_process()
            return self._publish(
                now=now,
                state=ScheduledTradingState.COMPLETED,
                business_day=True,
                next_action_at=None,
                message=(
                    "Today's scheduled operation is complete."
                ),
            )

        self._refresh_process_state()

        if self.process is None:
            if (
                self.autonomous_guard_enabled
                and not self._run_autonomous_guard()
            ):
                return self._publish(
                    now=now,
                    state=ScheduledTradingState.FAILED,
                    business_day=True,
                    next_action_at=self._next_action(
                        now,
                        local_time,
                    ),
                    message=(
                        "Autonomous Operation Guard blocked "
                        "Paper Trading startup. "
                        "autonomous_operation_report.jsonを"
                        "確認してください。"
                    ),
                )

            if (
                self.readiness_check_enabled
                and not self._run_readiness_check()
            ):
                return self._publish(
                    now=now,
                    state=ScheduledTradingState.FAILED,
                    business_day=True,
                    next_action_at=self._next_action(
                        now,
                        local_time,
                    ),
                    message=(
                        "Paper Trading preflight check failed. "
                        "kabuステーション、APIトークン、"
                        "Watchlist、Databaseを確認してください。"
                    ),
                )

            self._start_process()

        state = (
            ScheduledTradingState.LUNCH_BREAK
            if (
                self.settings.lunch_start_at
                <= local_time
                < self.settings.lunch_end_at
            )
            else ScheduledTradingState.RUNNING
        )

        return self._publish(
            now=now,
            state=state,
            business_day=True,
            next_action_at=self._next_action(
                now,
                local_time,
            ),
            message=(
                "run_market_session is active. "
                "Lunch handling is delegated to "
                "MarketSessionRunner."
            ),
        )

    def run_forever(
        self,
        *,
        poll_interval_seconds: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError(
                "監視間隔は0より大きい必要があります。"
            )

        try:
            while not self._stop_requested:
                self.run_once()
                sleep(poll_interval_seconds)
        finally:
            self._stop_process()

    def request_stop(self) -> None:
        self._stop_requested = True

    def _run_autonomous_guard(self) -> bool:
        self.autonomous_guard_report_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.run_autonomous_operation_validation",
                "--output-path",
                str(self.autonomous_guard_report_path),
            ],
            check=False,
            cwd=Path.cwd(),
            timeout=self.autonomous_guard_timeout_seconds,
        )
        return completed.returncode == 0

    def _run_readiness_check(self) -> bool:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.run_paper_trading",
                "--check",
            ],
            check=False,
            cwd=Path.cwd(),
            timeout=self.readiness_timeout_seconds,
        )
        return completed.returncode == 0

    def _start_process(self) -> None:
        command = [
            sys.executable,
            "-m",
            "app.run_market_session",
            *self.paper_arguments,
        ]
        self.process = self.popen_factory(
            command,
            cwd=Path.cwd(),
        )

    def _refresh_process_state(self) -> None:
        if self.process is None:
            return

        exit_code = self.process.poll()

        if exit_code is None:
            return

        self.last_exit_code = int(exit_code)
        self.process = None

    def _stop_process(self) -> None:
        if self.process is None:
            return

        if self.process.poll() is None:
            self.process.terminate()

            try:
                self.process.wait(timeout=15.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

        self.last_exit_code = (
            self.process.returncode
        )
        self.process = None

    def _publish(
        self,
        *,
        now: datetime,
        state: ScheduledTradingState,
        business_day: bool,
        next_action_at: datetime | None,
        message: str,
    ) -> ScheduledTradingStatus:
        status = ScheduledTradingStatus(
            generated_at=now,
            trading_date=now.date(),
            state=state,
            business_day=business_day,
            enabled=self.enabled,
            process_id=(
                self.process.pid
                if self.process is not None
                and self.process.poll() is None
                else None
            ),
            last_exit_code=self.last_exit_code,
            next_action_at=next_action_at,
            message=message,
            settings=self.settings,
        )
        self.status_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        temporary = self.status_path.with_suffix(
            self.status_path.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(
                status.to_dict(),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(self.status_path)
        return status

    def _next_action(
        self,
        now: datetime,
        local_time: clock_time,
    ) -> datetime:
        candidates = [
            value
            for value in (
                self.settings.lunch_start_at,
                self.settings.lunch_end_at,
                self.settings.market_close_at,
                self.settings.stop_at,
            )
            if value > local_time
        ]
        return self._at(
            now,
            candidates[0],
        )

    @staticmethod
    def _at(
        now: datetime,
        target: clock_time,
    ) -> datetime:
        return datetime.combine(
            now.date(),
            target,
            tzinfo=TOKYO,
        )

    def _current_time(self) -> datetime:
        value = self.now_provider()

        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return value.astimezone(TOKYO)
