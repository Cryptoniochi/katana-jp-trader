"""営業日8:40にMorning Pre-Flightを自動実行する。"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.market.market_calendar import TokyoMarketCalendar
from app.runtime.morning_preflight_schedule_models import (
    MorningPreflightScheduleSettings,
    MorningPreflightScheduleState,
    MorningPreflightScheduleStatus,
)


TOKYO = ZoneInfo("Asia/Tokyo")
DEFAULT_STATUS_PATH = Path(
    "reports/service/morning_preflight_schedule.json"
)
DEFAULT_MARKER_DIRECTORY = Path(
    "reports/service/morning_preflight"
)


class MorningPreflightScheduler:
    """営業日8:40のMorning Checkを自動実行する。"""

    def __init__(
        self,
        *,
        enabled: bool,
        status_path: Path = DEFAULT_STATUS_PATH,
        marker_directory: Path = DEFAULT_MARKER_DIRECTORY,
        settings: MorningPreflightScheduleSettings | None = None,
        calendar: TokyoMarketCalendar | None = None,
        now_provider: Callable[[], datetime] | None = None,
        command_runner: Callable[..., subprocess.CompletedProcess] = (
            subprocess.run
        ),
        monotonic_provider: Callable[[], float] = time.monotonic,
    ) -> None:
        self.enabled = enabled
        self.status_path = Path(status_path)
        self.marker_directory = Path(marker_directory)
        self.settings = (
            settings
            if settings is not None
            else MorningPreflightScheduleSettings()
        )
        self.calendar = (
            calendar
            if calendar is not None
            else TokyoMarketCalendar()
        )
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(TOKYO)
        )
        self.command_runner = command_runner
        self.monotonic_provider = monotonic_provider

        self.last_attempt_at: datetime | None = None
        self.last_exit_code: int | None = None
        self._retry_after_monotonic = 0.0
        self._stop_requested = False

    def run_once(
        self,
    ) -> MorningPreflightScheduleStatus:
        """現在時刻に必要な処理を1回だけ実行する。"""

        now = self._current_time()
        target_date = now.date()
        business_day = self.calendar.is_business_day(
            target_date
        )

        if not self.enabled:
            return self._publish(
                now=now,
                state=MorningPreflightScheduleState.DISABLED,
                business_day=business_day,
                next_action_at=None,
                message=(
                    "Morning Pre-Flight schedule is disabled."
                ),
            )

        if not business_day:
            return self._publish(
                now=now,
                state=MorningPreflightScheduleState.CLOSED_DAY,
                business_day=False,
                next_action_at=None,
                message="Tokyo market is closed today.",
            )

        scheduled_at = datetime.combine(
            target_date,
            self.settings.run_at,
            tzinfo=TOKYO,
        )

        if now < scheduled_at:
            return self._publish(
                now=now,
                state=MorningPreflightScheduleState.WAITING,
                business_day=True,
                next_action_at=scheduled_at,
                message=(
                    "Waiting for the 08:40 Morning Pre-Flight."
                ),
            )

        marker_path = self._marker_path(
            target_date
        )

        if marker_path.exists():
            return self._publish(
                now=now,
                state=MorningPreflightScheduleState.COMPLETED,
                business_day=True,
                next_action_at=None,
                message=(
                    "Morning Pre-Flight was already "
                    "sent today."
                ),
            )

        monotonic_now = self.monotonic_provider()

        if monotonic_now < self._retry_after_monotonic:
            return self._publish(
                now=now,
                state=MorningPreflightScheduleState.RETRY_WAIT,
                business_day=True,
                next_action_at=None,
                message=(
                    "Waiting before the next Morning "
                    "Pre-Flight retry."
                ),
            )

        self.last_attempt_at = now
        self._publish(
            now=now,
            state=MorningPreflightScheduleState.RUNNING,
            business_day=True,
            next_action_at=None,
            message=(
                "Running Morning Pre-Flight notification."
            ),
        )

        completed = self.command_runner(
            [
                sys.executable,
                "-m",
                "app.run_morning_preflight",
            ],
            check=False,
            cwd=Path.cwd(),
            timeout=self.settings.command_timeout_seconds,
        )
        self.last_exit_code = int(
            completed.returncode
        )

        if completed.returncode != 0:
            self._retry_after_monotonic = (
                self.monotonic_provider()
                + self.settings.retry_interval_seconds
            )
            return self._publish(
                now=now,
                state=MorningPreflightScheduleState.FAILED,
                business_day=True,
                next_action_at=None,
                message=(
                    "Morning Pre-Flight failed. "
                    f"exit_code={completed.returncode}"
                ),
            )

        marker_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        marker_path.write_text(
            json.dumps(
                {
                    "target_date": target_date.isoformat(),
                    "completed_at": now.isoformat(),
                    "exit_code": self.last_exit_code,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return self._publish(
            now=now,
            state=MorningPreflightScheduleState.COMPLETED,
            business_day=True,
            next_action_at=None,
            message=(
                "Morning Pre-Flight notification completed."
            ),
        )

    def run_forever(
        self,
        *,
        poll_interval_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError(
                "監視間隔は0より大きい必要があります。"
            )

        while not self._stop_requested:
            self.run_once()
            sleep(poll_interval_seconds)

    def request_stop(self) -> None:
        self._stop_requested = True

    def _marker_path(
        self,
        target_date,
    ) -> Path:
        return (
            self.marker_directory
            / f"{target_date.isoformat()}.sent.json"
        )

    def _publish(
        self,
        *,
        now: datetime,
        state: MorningPreflightScheduleState,
        business_day: bool,
        next_action_at: datetime | None,
        message: str,
    ) -> MorningPreflightScheduleStatus:
        status = MorningPreflightScheduleStatus(
            generated_at=now,
            target_date=now.date(),
            state=state,
            business_day=business_day,
            enabled=self.enabled,
            next_action_at=next_action_at,
            last_attempt_at=self.last_attempt_at,
            last_exit_code=self.last_exit_code,
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

    def _current_time(self) -> datetime:
        value = self.now_provider()

        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return value.astimezone(TOKYO)
