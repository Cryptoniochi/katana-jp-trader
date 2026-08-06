"""営業日15:36に候補ユニバース日足を自動収集する。"""

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
from app.runtime.universe_daily_schedule_models import (
    UniverseDailyScheduleSettings,
    UniverseDailyScheduleState,
    UniverseDailyScheduleStatus,
)


TOKYO = ZoneInfo("Asia/Tokyo")


class UniverseDailyScheduler:
    """引け後の日足収集を1営業日1回管理する。"""

    def __init__(
        self,
        *,
        enabled: bool,
        database_path: Path = Path("data/katana.db"),
        status_path: Path = Path(
            "reports/service/universe_daily_schedule.json"
        ),
        report_path: Path = Path(
            "reports/universe/"
            "kabu_station_daily_latest.json"
        ),
        marker_directory: Path = Path(
            "reports/service/universe_daily"
        ),
        settings: UniverseDailyScheduleSettings | None = None,
        calendar: TokyoMarketCalendar | None = None,
        now_provider: Callable[[], datetime] | None = None,
        command_runner=subprocess.run,
        monotonic_provider: Callable[[], float] = time.monotonic,
    ) -> None:
        self.enabled = enabled
        self.database_path = Path(database_path)
        self.status_path = Path(status_path)
        self.report_path = Path(report_path)
        self.marker_directory = Path(marker_directory)
        self.settings = (
            settings
            if settings is not None
            else UniverseDailyScheduleSettings()
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

    def run_once(self) -> UniverseDailyScheduleStatus:
        now = self._current_time()
        target_date = now.date()
        business_day = self.calendar.is_business_day(
            target_date
        )

        if not self.enabled:
            return self._publish(
                now=now,
                state=UniverseDailyScheduleState.DISABLED,
                business_day=business_day,
                next_action_at=None,
                requested_count=None,
                collected_count=None,
                success_ratio=None,
                message="Universe Daily schedule is disabled.",
            )

        if not business_day:
            return self._publish(
                now=now,
                state=UniverseDailyScheduleState.CLOSED_DAY,
                business_day=False,
                next_action_at=None,
                requested_count=None,
                collected_count=None,
                success_ratio=None,
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
                state=UniverseDailyScheduleState.WAITING,
                business_day=True,
                next_action_at=scheduled_at,
                requested_count=None,
                collected_count=None,
                success_ratio=None,
                message="Waiting for the 15:36 universe daily collection.",
            )

        marker_path = (
            self.marker_directory
            / f"{target_date.isoformat()}.completed.json"
        )
        if marker_path.exists():
            payload = self._read_report()
            return self._publish(
                now=now,
                state=UniverseDailyScheduleState.COMPLETED,
                business_day=True,
                next_action_at=None,
                requested_count=payload.get("requested_count"),
                collected_count=payload.get("collected_count"),
                success_ratio=payload.get("success_ratio"),
                message=(
                    "Universe Daily collection was already "
                    "completed today."
                ),
            )

        if self.monotonic_provider() < self._retry_after_monotonic:
            return self._publish(
                now=now,
                state=UniverseDailyScheduleState.RETRY_WAIT,
                business_day=True,
                next_action_at=None,
                requested_count=None,
                collected_count=None,
                success_ratio=None,
                message="Waiting before the next universe daily retry.",
            )

        self.last_attempt_at = now
        self._publish(
            now=now,
            state=UniverseDailyScheduleState.RUNNING,
            business_day=True,
            next_action_at=None,
            requested_count=None,
            collected_count=None,
            success_ratio=None,
            message="Collecting universe daily bars.",
        )

        try:
            completed = self.command_runner(
                [
                    sys.executable,
                    "-m",
                    "app.run_collect_universe_daily_bars",
                    "--database-path",
                    str(self.database_path),
                    "--report-path",
                    str(self.report_path),
                    "--minimum-success-ratio",
                    str(self.settings.minimum_success_ratio),
                    "--trading-date",
                    target_date.isoformat(),
                ],
                check=False,
                cwd=Path.cwd(),
                timeout=self.settings.command_timeout_seconds,
            )
            self.last_exit_code = int(completed.returncode)
        except subprocess.TimeoutExpired:
            self.last_exit_code = -1

        payload = self._read_report()
        requested_count = self._as_int(
            payload.get("requested_count")
        )
        collected_count = self._as_int(
            payload.get("collected_count")
        )
        success_ratio = self._as_float(
            payload.get("success_ratio")
        )
        report_date = str(
            payload.get("trading_date") or ""
        )

        success = (
            self.last_exit_code == 0
            and report_date == target_date.isoformat()
            and requested_count is not None
            and requested_count > 0
            and collected_count is not None
            and collected_count > 0
            and success_ratio is not None
            and success_ratio
            >= self.settings.minimum_success_ratio
        )

        if not success:
            self._retry_after_monotonic = (
                self.monotonic_provider()
                + self.settings.retry_interval_seconds
            )
            return self._publish(
                now=now,
                state=UniverseDailyScheduleState.FAILED,
                business_day=True,
                next_action_at=None,
                requested_count=requested_count,
                collected_count=collected_count,
                success_ratio=success_ratio,
                message=(
                    "Universe Daily collection failed. "
                    f"exit_code={self.last_exit_code} "
                    f"report_date={report_date} "
                    f"requested={requested_count} "
                    f"collected={collected_count} "
                    f"success_ratio={success_ratio}"
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
                    "requested_count": requested_count,
                    "collected_count": collected_count,
                    "success_ratio": success_ratio,
                    "exit_code": self.last_exit_code,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return self._publish(
            now=now,
            state=UniverseDailyScheduleState.COMPLETED,
            business_day=True,
            next_action_at=None,
            requested_count=requested_count,
            collected_count=collected_count,
            success_ratio=success_ratio,
            message=(
                "Universe Daily collection completed. "
                f"collected={collected_count}/{requested_count}"
            ),
        )

    def run_forever(
        self,
        *,
        poll_interval_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        while not self._stop_requested:
            self.run_once()
            sleep(poll_interval_seconds)

    def request_stop(self) -> None:
        self._stop_requested = True

    def _read_report(self) -> dict[str, object]:
        if not self.report_path.exists():
            return {}
        try:
            payload = json.loads(
                self.report_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _publish(
        self,
        *,
        now: datetime,
        state: UniverseDailyScheduleState,
        business_day: bool,
        next_action_at: datetime | None,
        requested_count: int | None,
        collected_count: int | None,
        success_ratio: float | None,
        message: str,
    ) -> UniverseDailyScheduleStatus:
        status = UniverseDailyScheduleStatus(
            generated_at=now,
            target_date=now.date().isoformat(),
            state=state,
            business_day=business_day,
            enabled=self.enabled,
            next_action_at=next_action_at,
            last_attempt_at=self.last_attempt_at,
            last_exit_code=self.last_exit_code,
            requested_count=requested_count,
            collected_count=collected_count,
            success_ratio=success_ratio,
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

    @staticmethod
    def _as_int(value) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_float(value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _current_time(self) -> datetime:
        value = self.now_provider()
        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )
        return value.astimezone(TOKYO)
