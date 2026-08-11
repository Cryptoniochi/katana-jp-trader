"""営業日15:40にDaily Reportを生成・通知する。"""

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
from app.runtime.daily_report_schedule_models import (
    DailyReportScheduleSettings,
    DailyReportScheduleState,
    DailyReportScheduleStatus,
)


TOKYO = ZoneInfo("Asia/Tokyo")
DEFAULT_STATUS_PATH = Path(
    "reports/service/daily_report_schedule.json"
)
DEFAULT_MARKER_DIRECTORY = Path(
    "reports/daily/notifications"
)


class DailyReportScheduler:
    """日次レポート生成CLIと通知CLIを順番に実行する。"""

    def __init__(
        self,
        *,
        enabled: bool,
        database_path: Path,
        report_directory: Path = Path("reports/daily"),
        status_path: Path = DEFAULT_STATUS_PATH,
        marker_directory: Path = DEFAULT_MARKER_DIRECTORY,
        settings: DailyReportScheduleSettings | None = None,
        calendar: TokyoMarketCalendar | None = None,
        now_provider: Callable[[], datetime] | None = None,
        command_runner: Callable[..., subprocess.CompletedProcess] = (
            subprocess.run
        ),
        monotonic_provider: Callable[[], float] = time.monotonic,
    ) -> None:
        self.enabled = enabled
        self.database_path = Path(database_path)
        self.report_directory = Path(report_directory)
        self.status_path = Path(status_path)
        self.marker_directory = Path(marker_directory)
        self.settings = (
            settings
            if settings is not None
            else DailyReportScheduleSettings()
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
        self.report_exit_code: int | None = None
        self.validation_exit_code: int | None = None
        self.notification_exit_code: int | None = None
        self._retry_after_monotonic = 0.0
        self._stop_requested = False

    def run_once(self) -> DailyReportScheduleStatus:
        """現在時刻に必要な処理を1回だけ実行する。"""

        now = self._current_time()
        report_date = now.date()
        business_day = self.calendar.is_business_day(
            report_date
        )

        if not self.enabled:
            return self._publish(
                now=now,
                state=DailyReportScheduleState.DISABLED,
                business_day=business_day,
                next_action_at=None,
                message="Daily Report schedule is disabled.",
            )

        if not business_day:
            return self._publish(
                now=now,
                state=DailyReportScheduleState.CLOSED_DAY,
                business_day=False,
                next_action_at=None,
                message="Tokyo market is closed today.",
            )

        scheduled_at = datetime.combine(
            report_date,
            self.settings.run_at,
            tzinfo=TOKYO,
        )

        if now < scheduled_at:
            return self._publish(
                now=now,
                state=DailyReportScheduleState.WAITING,
                business_day=True,
                next_action_at=scheduled_at,
                message="Waiting for the 15:40 Daily Report run.",
            )

        marker_path = self._marker_path(
            report_date
        )

        if marker_path.exists():
            return self._publish(
                now=now,
                state=DailyReportScheduleState.COMPLETED,
                business_day=True,
                next_action_at=None,
                message=(
                    "Daily Report was already generated "
                    "and notified today."
                ),
            )

        monotonic_now = self.monotonic_provider()

        if monotonic_now < self._retry_after_monotonic:
            return self._publish(
                now=now,
                state=DailyReportScheduleState.RETRY_WAIT,
                business_day=True,
                next_action_at=None,
                message="Waiting before the next retry.",
            )

        self.last_attempt_at = now
        self._publish(
            now=now,
            state=DailyReportScheduleState.RUNNING,
            business_day=True,
            next_action_at=None,
            message="Generating and notifying Daily Report.",
        )

        report_result = self._run_report_command(
            report_date
        )
        self.report_exit_code = int(
            report_result.returncode
        )

        if report_result.returncode != 0:
            return self._schedule_retry(
                now=now,
                business_day=True,
                message=(
                    "Daily Report generation failed. "
                    f"exit_code={report_result.returncode}"
                ),
            )

        validation_result = (
            self._run_full_day_validation_command(
                report_date
            )
        )
        self.validation_exit_code = int(
            validation_result.returncode
        )

        if validation_result.returncode != 0:
            return self._schedule_retry(
                now=now,
                business_day=True,
                message=(
                    "Full-Day Validation failed. "
                    f"exit_code={validation_result.returncode}"
                ),
            )

        notification_result = (
            self._run_notification_command(
                report_date
            )
        )
        self.notification_exit_code = int(
            notification_result.returncode
        )

        if notification_result.returncode != 0:
            return self._schedule_retry(
                now=now,
                business_day=True,
                message=(
                    "Daily Report notification failed. "
                    f"exit_code={notification_result.returncode}"
                ),
            )

        marker_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        marker_path.write_text(
            json.dumps(
                {
                    "report_date": report_date.isoformat(),
                    "completed_at": now.isoformat(),
                    "report_exit_code": self.report_exit_code,
                    "validation_exit_code": (
                        self.validation_exit_code
                    ),
                    "notification_exit_code": (
                        self.notification_exit_code
                    ),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return self._publish(
            now=now,
            state=DailyReportScheduleState.COMPLETED,
            business_day=True,
            next_action_at=None,
            message=(
                "Daily Report generation and notification "
                "completed."
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

    def _run_report_command(
        self,
        report_date,
    ) -> subprocess.CompletedProcess:
        return self.command_runner(
            [
                sys.executable,
                "-m",
                "app.run_daily_report",
                "--database-path",
                str(self.database_path),
                "--report-date",
                report_date.isoformat(),
                "--output-path",
                str(
                    self.report_directory
                    / f"{report_date.isoformat()}.json"
                ),
            ],
            check=False,
            cwd=Path.cwd(),
            timeout=self.settings.command_timeout_seconds,
        )

    def _run_full_day_validation_command(
        self,
        report_date,
    ) -> subprocess.CompletedProcess:
        return self.command_runner(
            [
                sys.executable,
                "-m",
                "app.run_full_day_validation",
                "--database-path",
                str(self.database_path),
                "--trading-date",
                report_date.isoformat(),
                "--daily-report-directory",
                str(self.report_directory),
            ],
            check=False,
            cwd=Path.cwd(),
            timeout=self.settings.command_timeout_seconds,
        )

    def _run_notification_command(
        self,
        report_date,
    ) -> subprocess.CompletedProcess:
        return self.command_runner(
            [
                sys.executable,
                "-m",
                "app.run_daily_report_notification",
                "--report-directory",
                str(self.report_directory),
                "--report-date",
                report_date.isoformat(),
            ],
            check=False,
            cwd=Path.cwd(),
            timeout=self.settings.command_timeout_seconds,
        )

    def _schedule_retry(
        self,
        *,
        now: datetime,
        business_day: bool,
        message: str,
    ) -> DailyReportScheduleStatus:
        self._retry_after_monotonic = (
            self.monotonic_provider()
            + self.settings.retry_interval_seconds
        )
        return self._publish(
            now=now,
            state=DailyReportScheduleState.FAILED,
            business_day=business_day,
            next_action_at=None,
            message=message,
        )

    def _marker_path(
        self,
        report_date,
    ) -> Path:
        return (
            self.marker_directory
            / f"{report_date.isoformat()}.sent.json"
        )

    def _publish(
        self,
        *,
        now: datetime,
        state: DailyReportScheduleState,
        business_day: bool,
        next_action_at: datetime | None,
        message: str,
    ) -> DailyReportScheduleStatus:
        status = DailyReportScheduleStatus(
            generated_at=now,
            report_date=now.date(),
            state=state,
            business_day=business_day,
            enabled=self.enabled,
            next_action_at=next_action_at,
            last_attempt_at=self.last_attempt_at,
            report_exit_code=self.report_exit_code,
            notification_exit_code=(
                self.notification_exit_code
            ),
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
