"""営業日15:36以降に全市場Universeを更新し、監査・一次選定まで自動実行する。"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.market.market_calendar import TokyoMarketCalendar
from app.runtime.universe_daily_history_audit_service import (
    UniverseDailyHistoryAuditService,
)
from app.runtime.universe_daily_schedule_models import (
    UniverseDailyScheduleSettings,
    UniverseDailyScheduleState,
    UniverseDailyScheduleStatus,
)


TOKYO = ZoneInfo("Asia/Tokyo")


class UniverseDailyScheduler:
    """全市場Bootstrap → Audit → Primary Screeningを営業日ごとに完了させる。"""

    def __init__(
        self,
        *,
        enabled: bool,
        database_path: Path = Path("data/katana.db"),
        status_path: Path = Path(
            "reports/service/universe_daily_schedule.json"
        ),
        report_path: Path = Path(
            "reports/universe/bootstrap_latest.json"
        ),
        primary_report_path: Path = Path(
            "reports/universe/primary_screening_latest.json"
        ),
        candidate_output_path: Path = Path(
            "data/universe_candidates.txt"
        ),
        unavailable_path: Path = Path(
            "reports/universe/bootstrap_unavailable.json"
        ),
        audit_report_path: Path = Path(
            "reports/universe/daily_history_audit_latest.json"
        ),
        crash_report_path: Path = Path(
            "reports/service/universe_daily_scheduler_crash.json"
        ),
        marker_directory: Path = Path(
            "reports/service/universe_daily"
        ),
        maximum_symbols_per_run: int = 50,
        maximum_primary_symbols: int = 300,
        maximum_purchase_amount: float = 950_000.0,
        minimum_completion_ratio: float = 0.99,
        bootstrap_timeout_seconds: float = 900.0,
        primary_timeout_seconds: float = 180.0,
        settings: UniverseDailyScheduleSettings | None = None,
        calendar: TokyoMarketCalendar | None = None,
        now_provider: Callable[[], datetime] | None = None,
        command_runner=subprocess.run,
        monotonic_provider: Callable[[], float] = time.monotonic,
        history_audit_service: UniverseDailyHistoryAuditService | None = None,
    ) -> None:
        if maximum_symbols_per_run <= 0:
            raise ValueError(
                "maximum_symbols_per_runは1以上である必要があります。"
            )
        if maximum_primary_symbols <= 0:
            raise ValueError(
                "maximum_primary_symbolsは1以上である必要があります。"
            )
        if maximum_purchase_amount <= 0:
            raise ValueError(
                "maximum_purchase_amountは0より大きい必要があります。"
            )
        if not 0 < minimum_completion_ratio <= 1:
            raise ValueError(
                "minimum_completion_ratioは0より大きく1以下である必要があります。"
            )

        self.enabled = enabled
        self.database_path = Path(database_path)
        self.status_path = Path(status_path)
        self.report_path = Path(report_path)
        self.primary_report_path = Path(primary_report_path)
        self.candidate_output_path = Path(candidate_output_path)
        self.unavailable_path = Path(unavailable_path)
        self.audit_report_path = Path(audit_report_path)
        self.crash_report_path = Path(crash_report_path)
        self.marker_directory = Path(marker_directory)
        self.maximum_symbols_per_run = int(maximum_symbols_per_run)
        self.maximum_primary_symbols = int(maximum_primary_symbols)
        self.maximum_purchase_amount = float(maximum_purchase_amount)
        self.minimum_completion_ratio = float(minimum_completion_ratio)
        self.bootstrap_timeout_seconds = float(bootstrap_timeout_seconds)
        self.primary_timeout_seconds = float(primary_timeout_seconds)
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
        self.history_audit_service = (
            history_audit_service
            if history_audit_service is not None
            else UniverseDailyHistoryAuditService(
                database_path=self.database_path,
                minimum_effective_coverage_ratio=(
                    self.minimum_completion_ratio
                ),
                terminal_skip_path=self.unavailable_path,
            )
        )
        self.last_attempt_at: datetime | None = None
        self.last_exit_code: int | None = None
        self._retry_after_monotonic = 0.0
        self._stop_requested = False

    def run_once(self) -> UniverseDailyScheduleStatus:
        now = self._current_time()
        target_date = now.date()
        business_day = self.calendar.is_business_day(target_date)

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
                message=(
                    "Waiting for the 15:36 full-market "
                    "Universe pipeline."
                ),
            )

        marker_path = (
            self.marker_directory
            / f"{target_date.isoformat()}.completed.json"
        )
        if marker_path.exists():
            marker = self._read_json(marker_path)
            return self._publish(
                now=now,
                state=UniverseDailyScheduleState.COMPLETED,
                business_day=True,
                next_action_at=None,
                requested_count=self._as_int(
                    marker.get("universe_count")
                ),
                collected_count=self._as_int(
                    marker.get("daily_bar_count")
                ),
                success_ratio=self._as_float(
                    marker.get("effective_coverage_ratio")
                    or marker.get("coverage_ratio")
                ),
                message=(
                    "Full-market Universe pipeline was already "
                    "completed today. "
                    f"primary_selected={marker.get('primary_selected_count')}"
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
                message=(
                    "Waiting before the next full-market "
                    "Universe pipeline retry."
                ),
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
            message=(
                "Updating full-market daily bars. "
                f"batch_size={self.maximum_symbols_per_run}"
            ),
        )

        bootstrap_exit_code = self._run_bootstrap(
            target_date=target_date
        )
        self.last_exit_code = bootstrap_exit_code
        payload = self._read_json(self.report_path)

        if "requested_count" in payload:
            return self._handle_legacy_report(
                now=now,
                target_date=target_date,
                business_day=business_day,
                marker_path=marker_path,
                payload=payload,
                exit_code=bootstrap_exit_code,
            )

        universe_count = self._as_int(payload.get("universe_count"))
        remaining_count = self._as_int(payload.get("remaining_count"))
        retryable_remaining = self._as_int(
            payload.get("retryable_remaining_count")
        )
        terminal_skipped = self._as_int(
            payload.get("terminal_skipped_count")
        )
        coverage_ratio = self._as_float(payload.get("coverage_ratio"))
        bootstrap_completed = bool(payload.get("completed"))
        report_date = str(payload.get("trading_date") or "")

        daily_bar_count = (
            None
            if universe_count is None or remaining_count is None
            else universe_count - remaining_count
        )

        bootstrap_valid = (
            bootstrap_exit_code == 0
            and report_date == target_date.isoformat()
            and universe_count is not None
            and universe_count > 0
            and coverage_ratio is not None
        )

        if not bootstrap_valid:
            return self._fail(
                now=now,
                business_day=business_day,
                requested_count=universe_count,
                collected_count=daily_bar_count,
                success_ratio=coverage_ratio,
                message=(
                    "Full-market Bootstrap failed or produced "
                    "an invalid report. "
                    f"exit_code={bootstrap_exit_code} "
                    f"report_date={report_date}"
                ),
            )

        if not bootstrap_completed:
            return self._publish(
                now=now,
                state=UniverseDailyScheduleState.RUNNING,
                business_day=True,
                next_action_at=None,
                requested_count=universe_count,
                collected_count=daily_bar_count,
                success_ratio=coverage_ratio,
                message=(
                    "Full-market Bootstrap is continuing. "
                    f"daily_bars={daily_bar_count}/{universe_count} "
                    f"retryable_remaining={retryable_remaining} "
                    f"terminal_skipped={terminal_skipped}"
                ),
            )

        try:
            audit = self.history_audit_service.audit(
                trading_date=target_date
            )
        except Exception as error:
            return self._fail(
                now=now,
                business_day=business_day,
                requested_count=universe_count,
                collected_count=daily_bar_count,
                success_ratio=coverage_ratio,
                message=(
                    "Daily History Audit raised an error after "
                    "Bootstrap. "
                    f"{type(error).__name__}: {error}"
                ),
            )

        self._write_json_atomic(
            self.audit_report_path,
            audit.to_dict(),
        )

        if not audit.completed:
            return self._fail(
                now=now,
                business_day=business_day,
                requested_count=audit.active_universe_count,
                collected_count=audit.collected_count,
                success_ratio=audit.effective_coverage_ratio,
                message=(
                    "Daily History Audit failed. "
                    f"collected={audit.collected_count}/"
                    f"{audit.active_universe_count} "
                    f"terminal_skipped={audit.terminal_skipped_count} "
                    f"unexplained_missing={audit.unexplained_missing_count} "
                    f"effective_coverage="
                    f"{audit.effective_coverage_ratio:.4f}"
                ),
            )

        screening_exit_code = self._run_primary_screening()
        self.last_exit_code = screening_exit_code
        primary = self._read_json(self.primary_report_path)
        primary_selected = self._as_int(primary.get("selected_count"))
        primary_evaluated = self._as_int(primary.get("evaluated_count"))
        candidate_count = self._candidate_count()

        screening_success = (
            screening_exit_code == 0
            and primary_selected is not None
            and primary_selected > 0
            and candidate_count == primary_selected
            and candidate_count <= self.maximum_primary_symbols
        )

        if not screening_success:
            return self._fail(
                now=now,
                business_day=business_day,
                requested_count=audit.active_universe_count,
                collected_count=audit.collected_count,
                success_ratio=audit.effective_coverage_ratio,
                message=(
                    "Primary Screening failed after Daily "
                    "History Audit. "
                    f"exit_code={screening_exit_code} "
                    f"selected={primary_selected} "
                    f"candidate_file_count={candidate_count}"
                ),
            )

        marker_payload = {
            "target_date": target_date.isoformat(),
            "completed_at": now.isoformat(),
            "universe_count": audit.active_universe_count,
            "daily_bar_count": audit.collected_count,
            "remaining_count": audit.missing_count,
            "retryable_remaining_count": (
                audit.unexplained_missing_count
            ),
            "terminal_skipped_count": (
                audit.terminal_skipped_count
            ),
            "coverage_ratio": audit.collection_ratio,
            "effective_coverage_ratio": (
                audit.effective_coverage_ratio
            ),
            "audit_completed": audit.completed,
            "audit_report": str(self.audit_report_path),
            "primary_evaluated_count": primary_evaluated,
            "primary_selected_count": primary_selected,
            "candidate_output": str(self.candidate_output_path),
            "exit_code": screening_exit_code,
        }
        self._write_json_atomic(marker_path, marker_payload)

        return self._publish(
            now=now,
            state=UniverseDailyScheduleState.COMPLETED,
            business_day=True,
            next_action_at=None,
            requested_count=audit.active_universe_count,
            collected_count=audit.collected_count,
            success_ratio=audit.effective_coverage_ratio,
            message=(
                "Full-market Universe pipeline completed after "
                "Daily History Audit. "
                f"daily_bars={audit.collected_count}/"
                f"{audit.active_universe_count} "
                f"terminal_skipped={audit.terminal_skipped_count} "
                f"primary_selected={primary_selected}"
            ),
        )

    def _run_bootstrap(self, *, target_date) -> int:
        try:
            completed = self.command_runner(
                [
                    sys.executable,
                    "-m",
                    "app.run_universe_bootstrap",
                    "--database-path",
                    str(self.database_path),
                    "--trading-date",
                    target_date.isoformat(),
                    "--maximum-symbols-per-run",
                    str(self.maximum_symbols_per_run),
                    "--minimum-completion-ratio",
                    str(self.minimum_completion_ratio),
                    "--unavailable-path",
                    str(self.unavailable_path),
                    "--report-path",
                    str(self.report_path),
                ],
                check=False,
                cwd=Path.cwd(),
                timeout=self.bootstrap_timeout_seconds,
            )
            return int(completed.returncode)
        except subprocess.TimeoutExpired:
            return -1

    def _run_primary_screening(self) -> int:
        try:
            completed = self.command_runner(
                [
                    sys.executable,
                    "-m",
                    "app.run_universe_primary_screening",
                    "--database-path",
                    str(self.database_path),
                    "--maximum-symbols",
                    str(self.maximum_primary_symbols),
                    "--maximum-purchase-amount",
                    str(self.maximum_purchase_amount),
                    "--output-path",
                    str(self.primary_report_path),
                    "--candidate-output",
                    str(self.candidate_output_path),
                ],
                check=False,
                cwd=Path.cwd(),
                timeout=self.primary_timeout_seconds,
            )
            return int(completed.returncode)
        except subprocess.TimeoutExpired:
            return -1

    def _handle_legacy_report(
        self,
        *,
        now: datetime,
        target_date,
        business_day: bool,
        marker_path: Path,
        payload: dict[str, object],
        exit_code: int,
    ) -> UniverseDailyScheduleStatus:
        requested_count = self._as_int(payload.get("requested_count"))
        collected_count = self._as_int(payload.get("collected_count"))
        success_ratio = self._as_float(payload.get("success_ratio"))
        report_date = str(payload.get("trading_date") or "")

        success = (
            exit_code == 0
            and report_date == target_date.isoformat()
            and requested_count is not None
            and requested_count > 0
            and collected_count is not None
            and collected_count > 0
            and success_ratio is not None
            and success_ratio >= self.settings.minimum_success_ratio
        )

        if not success:
            return self._fail(
                now=now,
                business_day=business_day,
                requested_count=requested_count,
                collected_count=collected_count,
                success_ratio=success_ratio,
                message=(
                    "Legacy Universe Daily collection failed. "
                    f"exit_code={exit_code}"
                ),
            )

        self._write_json_atomic(
            marker_path,
            {
                "target_date": target_date.isoformat(),
                "completed_at": now.isoformat(),
                "universe_count": requested_count,
                "daily_bar_count": collected_count,
                "coverage_ratio": success_ratio,
                "primary_selected_count": None,
                "legacy_mode": True,
                "exit_code": exit_code,
            },
        )

        return self._publish(
            now=now,
            state=UniverseDailyScheduleState.COMPLETED,
            business_day=business_day,
            next_action_at=None,
            requested_count=requested_count,
            collected_count=collected_count,
            success_ratio=success_ratio,
            message="Legacy Universe Daily collection completed.",
        )

    def _fail(
        self,
        *,
        now: datetime,
        business_day: bool,
        requested_count: int | None,
        collected_count: int | None,
        success_ratio: float | None,
        message: str,
    ) -> UniverseDailyScheduleStatus:
        self._retry_after_monotonic = (
            self.monotonic_provider()
            + self.settings.retry_interval_seconds
        )
        return self._publish(
            now=now,
            state=UniverseDailyScheduleState.FAILED,
            business_day=business_day,
            next_action_at=None,
            requested_count=requested_count,
            collected_count=collected_count,
            success_ratio=success_ratio,
            message=message,
        )

    def run_forever(
        self,
        *,
        poll_interval_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Schedulerを継続実行し、1サイクルの予期しない例外から自己復旧する。"""

        while not self._stop_requested:
            try:
                self.run_once()
            except Exception as error:
                self._handle_unexpected_cycle_error(error)

            if not self._stop_requested:
                sleep(poll_interval_seconds)

    def _handle_unexpected_cycle_error(
        self,
        error: Exception,
    ) -> UniverseDailyScheduleStatus:
        """未捕捉例外を永続化し、FAILED状態にして次回再試行へつなぐ。"""

        now = self._current_time()
        business_day = self.calendar.is_business_day(now.date())
        formatted_traceback = "".join(
            traceback.format_exception(
                type(error),
                error,
                error.__traceback__,
            )
        )

        crash_payload = {
            "generated_at": now.isoformat(),
            "target_date": now.date().isoformat(),
            "exception_type": type(error).__name__,
            "exception_message": str(error),
            "traceback": formatted_traceback,
            "last_attempt_at": (
                None
                if self.last_attempt_at is None
                else self.last_attempt_at.isoformat()
            ),
            "last_exit_code": self.last_exit_code,
        }

        try:
            self._write_json_atomic(
                self.crash_report_path,
                crash_payload,
            )
        except Exception:
            # 障害レポート書き込み失敗がScheduler本体を終了させないようにする。
            pass

        self._retry_after_monotonic = (
            self.monotonic_provider()
            + self.settings.retry_interval_seconds
        )

        try:
            return self._publish(
                now=now,
                state=UniverseDailyScheduleState.FAILED,
                business_day=business_day,
                next_action_at=None,
                requested_count=None,
                collected_count=None,
                success_ratio=None,
                message=(
                    "Universe Daily Scheduler recovered from an "
                    "unexpected cycle error. "
                    f"{type(error).__name__}: {error}"
                ),
            )
        except Exception:
            # status保存自体の障害でもrun_foreverを生存させる。
            return UniverseDailyScheduleStatus(
                generated_at=now,
                target_date=now.date().isoformat(),
                state=UniverseDailyScheduleState.FAILED,
                business_day=business_day,
                enabled=self.enabled,
                next_action_at=None,
                last_attempt_at=self.last_attempt_at,
                last_exit_code=self.last_exit_code,
                requested_count=None,
                collected_count=None,
                success_ratio=None,
                message=(
                    "Universe Daily Scheduler recovered from an "
                    "unexpected cycle error, but status persistence "
                    "also failed. "
                    f"{type(error).__name__}: {error}"
                ),
                settings=self.settings,
            )

    def request_stop(self) -> None:
        self._stop_requested = True

    def _candidate_count(self) -> int:
        if not self.candidate_output_path.exists():
            return 0
        return len(
            {
                line.strip()
                for line in self.candidate_output_path.read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            }
        )

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _write_json_atomic(
        path: Path,
        payload: dict[str, object],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)

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
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.status_path.with_suffix(
            self.status_path.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(status.to_dict(), ensure_ascii=False, indent=2),
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
