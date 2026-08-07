"""営業日8:20にPrimary Universe限定のDynamic Watchlistを安全更新する。"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from app.dashboard.symbol_name_reader import SymbolNameReader
from app.market.market_calendar import TokyoMarketCalendar
from app.runtime.dynamic_watchlist_schedule_models import (
    DynamicWatchlistScheduleSettings,
    DynamicWatchlistScheduleState,
    DynamicWatchlistScheduleStatus,
)


TOKYO = ZoneInfo("Asia/Tokyo")
DEFAULT_STATUS_PATH = Path(
    "reports/service/dynamic_watchlist_schedule.json"
)
DEFAULT_REPORT_PATH = Path(
    "reports/watchlist/latest.json"
)
DEFAULT_MARKER_DIRECTORY = Path(
    "reports/service/dynamic_watchlist"
)


class SymbolNameResolver(Protocol):
    def resolve(
        self,
        codes: Sequence[str],
    ) -> dict[str, str]:
        ...


class DynamicWatchlistScheduler:
    """営業日8:20のDynamic Watchlist更新を管理する。"""

    def __init__(
        self,
        *,
        enabled: bool,
        database_path: Path = Path("data/katana.db"),
        watchlist_path: Path = Path("watchlist.txt"),
        report_directory: Path = Path("reports/watchlist"),
        status_path: Path = DEFAULT_STATUS_PATH,
        latest_report_path: Path = DEFAULT_REPORT_PATH,
        marker_directory: Path = DEFAULT_MARKER_DIRECTORY,
        candidate_universe_path: Path = Path(
            "data/universe_candidates.txt"
        ),
        settings: DynamicWatchlistScheduleSettings | None = None,
        calendar: TokyoMarketCalendar | None = None,
        now_provider: Callable[[], datetime] | None = None,
        command_runner: Callable[..., subprocess.CompletedProcess] = (
            subprocess.run
        ),
        monotonic_provider: Callable[[], float] = time.monotonic,
        symbol_name_resolver: SymbolNameResolver | None = None,
    ) -> None:
        self.enabled = enabled
        self.database_path = Path(database_path)
        self.watchlist_path = Path(watchlist_path)
        self.report_directory = Path(report_directory)
        self.status_path = Path(status_path)
        self.latest_report_path = Path(latest_report_path)
        self.marker_directory = Path(marker_directory)
        self.candidate_universe_path = Path(
            candidate_universe_path
        )
        self.settings = (
            settings
            if settings is not None
            else DynamicWatchlistScheduleSettings()
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
        self.symbol_name_resolver = (
            symbol_name_resolver
            if symbol_name_resolver is not None
            else SymbolNameReader(
                self.database_path
            )
        )
        self.last_attempt_at: datetime | None = None
        self.last_exit_code: int | None = None
        self._retry_after_monotonic = 0.0
        self._stop_requested = False

    def run_once(self) -> DynamicWatchlistScheduleStatus:
        now = self._current_time()
        target_date = now.date()
        business_day = self.calendar.is_business_day(
            target_date
        )

        if not self.enabled:
            return self._publish(
                now=now,
                state=DynamicWatchlistScheduleState.DISABLED,
                business_day=business_day,
                next_action_at=None,
                selected_count=None,
                applied=None,
                message="Dynamic Watchlist schedule is disabled.",
            )

        if not business_day:
            return self._publish(
                now=now,
                state=DynamicWatchlistScheduleState.CLOSED_DAY,
                business_day=False,
                next_action_at=None,
                selected_count=None,
                applied=None,
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
                state=DynamicWatchlistScheduleState.WAITING,
                business_day=True,
                next_action_at=scheduled_at,
                selected_count=None,
                applied=None,
                message="Waiting for the 08:20 Dynamic Watchlist update.",
            )

        marker_path = self._marker_path(
            target_date
        )

        if marker_path.exists():
            selected_count, applied = self._read_latest_result()
            refreshed_count = self._refresh_symbol_names_once(
                marker_path=marker_path,
            )
            message = "Dynamic Watchlist was already updated today."

            if refreshed_count is not None:
                message += (
                    " Symbol name cache was refreshed. "
                    f"resolved_count={refreshed_count}"
                )

            return self._publish(
                now=now,
                state=DynamicWatchlistScheduleState.COMPLETED,
                business_day=True,
                next_action_at=None,
                selected_count=selected_count,
                applied=applied,
                message=message,
            )

        if not self.candidate_universe_path.exists():
            return self._publish(
                now=now,
                state=DynamicWatchlistScheduleState.FAILED,
                business_day=True,
                next_action_at=None,
                selected_count=None,
                applied=False,
                message=(
                    "Primary Universe candidate file is missing: "
                    f"{self.candidate_universe_path}"
                ),
            )

        candidate_count = len(
            {
                line.strip()
                for line in self.candidate_universe_path.read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            }
        )
        if candidate_count <= 0:
            return self._publish(
                now=now,
                state=DynamicWatchlistScheduleState.FAILED,
                business_day=True,
                next_action_at=None,
                selected_count=0,
                applied=False,
                message=(
                    "Primary Universe candidate file is empty."
                ),
            )

        if self.monotonic_provider() < self._retry_after_monotonic:
            return self._publish(
                now=now,
                state=DynamicWatchlistScheduleState.RETRY_WAIT,
                business_day=True,
                next_action_at=None,
                selected_count=None,
                applied=False,
                message="Waiting before the next Dynamic Watchlist retry.",
            )

        self.last_attempt_at = now
        self._publish(
            now=now,
            state=DynamicWatchlistScheduleState.RUNNING,
            business_day=True,
            next_action_at=None,
            selected_count=None,
            applied=None,
            message=(
                "Generating Dynamic Watchlist from "
                f"{candidate_count} Primary Universe symbols."
            ),
        )

        completed = self.command_runner(
            [
                sys.executable,
                "-m",
                "app.run_dynamic_watchlist",
                "--database-path",
                str(self.database_path),
                "--watchlist-path",
                str(self.watchlist_path),
                "--report-directory",
                str(self.report_directory),
                "--capital-limit",
                str(self.settings.capital_limit),
                "--purchase-budget",
                str(self.settings.purchase_budget),
                "--minimum-symbols",
                str(self.settings.minimum_symbols),
                "--maximum-symbols",
                str(self.settings.maximum_symbols),
                "--require-candidate-universe",
                "--apply",
            ],
            check=False,
            cwd=Path.cwd(),
            timeout=self.settings.command_timeout_seconds,
        )
        self.last_exit_code = int(
            completed.returncode
        )
        selected_count, applied = (
            self._read_latest_result()
        )

        if (
            completed.returncode != 0
            or not applied
            or selected_count is None
            or selected_count
            < self.settings.minimum_symbols
        ):
            self._retry_after_monotonic = (
                self.monotonic_provider()
                + self.settings.retry_interval_seconds
            )
            return self._publish(
                now=now,
                state=DynamicWatchlistScheduleState.FAILED,
                business_day=True,
                next_action_at=None,
                selected_count=selected_count,
                applied=applied,
                message=(
                    "Dynamic Watchlist update failed. "
                    f"primary_candidates={candidate_count} "
                    f"exit_code={completed.returncode} "
                    f"selected_count={selected_count} "
                    f"applied={applied}"
                ),
            )

        resolved_name_count = (
            self._refresh_symbol_names()
        )

        marker_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        marker_path.write_text(
            json.dumps(
                {
                    "target_date": (
                        target_date.isoformat()
                    ),
                    "completed_at": now.isoformat(),
                    "primary_candidate_count": (
                        candidate_count
                    ),
                    "selected_count": selected_count,
                    "applied": applied,
                    "exit_code": self.last_exit_code,
                    "symbol_names_refreshed": True,
                    "resolved_symbol_name_count": (
                        resolved_name_count
                    ),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return self._publish(
            now=now,
            state=DynamicWatchlistScheduleState.COMPLETED,
            business_day=True,
            next_action_at=None,
            selected_count=selected_count,
            applied=applied,
            message=(
                "Dynamic Watchlist update completed. "
                f"primary_candidates={candidate_count} "
                f"selected_count={selected_count} "
                "resolved_symbol_name_count="
                f"{resolved_name_count}"
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

    def _read_latest_result(
        self,
    ) -> tuple[int | None, bool | None]:
        if not self.latest_report_path.exists():
            return None, None
        try:
            payload = json.loads(
                self.latest_report_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            return None, None

        selected = payload.get(
            "selected",
            [],
        )
        selected_count = (
            len(selected)
            if isinstance(selected, list)
            else None
        )
        applied = payload.get("applied")
        return (
            selected_count,
            bool(applied)
            if applied is not None
            else None,
        )

    def _refresh_symbol_names_once(
        self,
        *,
        marker_path: Path,
    ) -> int | None:
        try:
            marker = json.loads(
                marker_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            marker = {}

        if (
            isinstance(marker, dict)
            and marker.get(
                "symbol_names_refreshed"
            ) is True
        ):
            return None

        resolved_count = (
            self._refresh_symbol_names()
        )

        if not isinstance(marker, dict):
            marker = {}

        marker["symbol_names_refreshed"] = True
        marker[
            "resolved_symbol_name_count"
        ] = resolved_count

        temporary = marker_path.with_suffix(
            marker_path.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(
                marker,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(
            marker_path
        )
        return resolved_count

    def _refresh_symbol_names(self) -> int:
        codes = self._read_selected_codes()
        if not codes:
            return 0
        try:
            names = (
                self.symbol_name_resolver.resolve(
                    codes
                )
            )
        except Exception:
            return 0
        return len(names)

    def _read_selected_codes(
        self,
    ) -> tuple[str, ...]:
        if not self.latest_report_path.exists():
            return ()
        try:
            payload = json.loads(
                self.latest_report_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            return ()

        selected = payload.get(
            "selected",
            [],
        )
        if not isinstance(selected, list):
            return ()

        return tuple(
            dict.fromkeys(
                str(
                    candidate.get("code")
                    or ""
                ).strip()
                for candidate in selected
                if isinstance(candidate, dict)
                and str(
                    candidate.get("code")
                    or ""
                ).strip()
            )
        )

    def _marker_path(
        self,
        target_date,
    ) -> Path:
        return (
            self.marker_directory
            / (
                f"{target_date.isoformat()}"
                ".applied.json"
            )
        )

    def _publish(
        self,
        *,
        now: datetime,
        state: DynamicWatchlistScheduleState,
        business_day: bool,
        next_action_at: datetime | None,
        selected_count: int | None,
        applied: bool | None,
        message: str,
    ) -> DynamicWatchlistScheduleStatus:
        status = DynamicWatchlistScheduleStatus(
            generated_at=now,
            target_date=now.date(),
            state=state,
            business_day=business_day,
            enabled=self.enabled,
            next_action_at=next_action_at,
            last_attempt_at=self.last_attempt_at,
            last_exit_code=self.last_exit_code,
            selected_count=selected_count,
            applied=applied,
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
        temporary.replace(
            self.status_path
        )
        return status

    def _current_time(self) -> datetime:
        value = self.now_provider()
        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )
        return value.astimezone(TOKYO)
