"""Project KATANAの1営業日全体を横断検証する。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from app.runtime.paper_trading_daily_repository import (
    PaperTradingDailyRecord,
    PaperTradingDailySummaryRepository,
)


class PaperTradingDailyRecordReader(Protocol):
    """Paper Trading日次レコードの読取インターフェース。"""

    def get(
        self,
        trading_date: date,
    ) -> PaperTradingDailyRecord | None:
        """指定営業日の保存レコードを返す。"""


@dataclass(frozen=True, slots=True)
class FullDayValidationCheck:
    """1件の終日検証チェック結果。"""

    key: str
    label: str
    passed: bool
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "passed": self.passed,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class FullDayValidationResult:
    """終日検証結果。"""

    generated_at: datetime
    trading_date: date
    passed: bool
    checks: tuple[FullDayValidationCheck, ...]
    runtime: dict[str, object]
    integrity: dict[str, object]
    daily_summary: dict[str, object]
    daily_report: dict[str, object]

    @property
    def failed_check_count(self) -> int:
        return sum(not check.passed for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "trading_date": self.trading_date.isoformat(),
            "passed": self.passed,
            "failed_check_count": self.failed_check_count,
            "checks": [
                check.to_dict()
                for check in self.checks
            ],
            "runtime": self.runtime,
            "integrity": self.integrity,
            "daily_summary": self.daily_summary,
            "daily_report": self.daily_report,
        }


class FullDayValidationService:
    """Runtime・Integrity・日次保存・Daily Reportを横断検証する。"""

    def __init__(
        self,
        *,
        database_path: Path,
        runtime_status_path: Path = Path(
            "reports/service/paper_trading_runtime_status.json"
        ),
        integrity_report_path: Path = Path(
            "reports/service/watchlist_execution_integrity.json"
        ),
        integrity_history_directory: Path = Path(
            "reports/service/"
            "watchlist_execution_integrity_history"
        ),
        daily_report_directory: Path = Path("reports/daily"),
        daily_repository: PaperTradingDailyRecordReader | None = None,
        now_provider=None,
        pnl_tolerance: float = 0.01,
    ) -> None:
        self.database_path = Path(database_path)
        self.runtime_status_path = Path(runtime_status_path)
        self.integrity_report_path = Path(integrity_report_path)
        self.integrity_history_directory = Path(
            integrity_history_directory
        )
        self.daily_report_directory = Path(daily_report_directory)
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self.pnl_tolerance = float(pnl_tolerance)

        if self.pnl_tolerance < 0:
            raise ValueError(
                "P/L許容差は0以上である必要があります。"
            )

        self.daily_repository = (
            daily_repository
            if daily_repository is not None
            else PaperTradingDailySummaryRepository(
                self.database_path,
                now_provider=self.now_provider,
            )
        )

    def validate(
        self,
        *,
        trading_date: date,
    ) -> FullDayValidationResult:
        """指定営業日の全経路を検証する。"""

        runtime = self._read_json(
            self.runtime_status_path
        )
        integrity = self._read_integrity_for_date(
            trading_date
        )
        daily_report = self._read_json(
            self.daily_report_directory
            / f"{trading_date.isoformat()}.json"
        )
        daily_record = self.daily_repository.get(
            trading_date
        )

        checks: list[FullDayValidationCheck] = []

        self._check_source_date(
            checks,
            key="runtime_date",
            label="Runtime trading date",
            payload=runtime,
            expected=trading_date,
        )
        self._check_source_date(
            checks,
            key="integrity_date",
            label="Integrity trading date",
            payload=integrity,
            expected=trading_date,
        )
        self._check_report_date(
            checks,
            payload=daily_report,
            expected=trading_date,
        )

        runtime_completed = (
            str(runtime.get("state") or "").lower()
            == "completed"
        )
        checks.append(
            FullDayValidationCheck(
                key="runtime_completed",
                label="Runtime completed",
                passed=runtime_completed,
                message=(
                    "Runtime completed normally."
                    if runtime_completed
                    else (
                        "Runtime state is not completed. "
                        f"state={runtime.get('state')}"
                    )
                ),
            )
        )

        failed_cycles = self._integer(
            runtime.get("failed_cycle_count")
        )
        checks.append(
            FullDayValidationCheck(
                key="runtime_failed_cycles",
                label="Failed cycles",
                passed=failed_cycles == 0,
                message=(
                    f"failed_cycle_count={failed_cycles}"
                ),
            )
        )

        runtime_positions = max(
            self._integer(
                runtime.get("open_position_count")
            ),
            self._integer(
                runtime.get("portfolio_position_count")
            ),
        )
        checks.append(
            FullDayValidationCheck(
                key="end_of_day_positions",
                label="End-of-day positions",
                passed=runtime_positions == 0,
                message=(
                    f"remaining_position_count={runtime_positions}"
                ),
            )
        )

        pnl_consistent = runtime.get(
            "pnl_consistent"
        )
        reconciliation_difference = self._float_or_none(
            runtime.get("pnl_reconciliation_difference")
        )
        runtime_pnl_ok = (
            pnl_consistent is not False
            and (
                reconciliation_difference is None
                or abs(reconciliation_difference)
                <= self.pnl_tolerance
            )
        )
        checks.append(
            FullDayValidationCheck(
                key="runtime_pnl_reconciliation",
                label="Runtime P/L reconciliation",
                passed=runtime_pnl_ok,
                message=(
                    "Runtime P/L reconciliation is consistent."
                    if runtime_pnl_ok
                    else (
                        "Runtime P/L reconciliation mismatch. "
                        f"difference={reconciliation_difference}"
                    )
                ),
            )
        )

        integrity_date_matches = (
            str(integrity.get("trading_date") or "")
            == trading_date.isoformat()
        )
        integrity_ok = (
            integrity_date_matches
            and bool(integrity.get("integrity_ok"))
        )
        checks.append(
            FullDayValidationCheck(
                key="watchlist_execution_integrity",
                label="Watchlist-to-Execution integrity",
                passed=integrity_ok,
                message=(
                    "Watchlist-to-Execution integrity passed."
                    if integrity_ok
                    else (
                        "Integrity report is stale for the "
                        "requested trading date."
                        if not integrity_date_matches
                        else (
                            "Watchlist-to-Execution integrity "
                            "failed."
                        )
                    )
                ),
            )
        )

        daily_summary_payload = self._daily_record_payload(
            daily_record
        )
        daily_summary_completed = (
            daily_record is not None
            and str(
                getattr(
                    daily_record.status,
                    "value",
                    daily_record.status,
                )
            ).lower()
            == "completed"
        )
        checks.append(
            FullDayValidationCheck(
                key="daily_summary_completed",
                label="Daily summary persisted",
                passed=daily_summary_completed,
                message=(
                    "Paper Trading daily summary is completed."
                    if daily_summary_completed
                    else (
                        "Completed Paper Trading daily summary "
                        "was not found."
                    )
                ),
            )
        )

        report_status = str(
            daily_report.get("status") or ""
        ).lower()
        report_valid = (
            report_status in {"complete", "empty"}
        )
        checks.append(
            FullDayValidationCheck(
                key="daily_report_generated",
                label="Daily report generated",
                passed=report_valid,
                message=(
                    f"daily_report_status={report_status or 'missing'}"
                ),
            )
        )

        runtime_execution_count = self._integer(
            runtime.get("execution_count")
        )
        integrity_execution_count = self._integer(
            integrity.get("execution_count")
        )
        daily_summary_execution_count = (
            None
            if daily_record is None
            else int(daily_record.execution_count)
        )

        execution_counts_ok = (
            daily_record is not None
            and runtime_execution_count
            == integrity_execution_count
            == daily_summary_execution_count
        )
        checks.append(
            FullDayValidationCheck(
                key="execution_count_reconciliation",
                label="Execution count reconciliation",
                passed=execution_counts_ok,
                message=(
                    "runtime="
                    f"{runtime_execution_count}, "
                    "integrity="
                    f"{integrity_execution_count}, "
                    "daily_summary="
                    f"{daily_summary_execution_count}"
                ),
            )
        )

        runtime_signal_count = self._integer(
            runtime.get("signal_count")
        )
        integrity_signal_count = self._integer(
            integrity.get("signal_count")
        )
        daily_summary_signal_count = (
            None
            if daily_record is None
            else int(daily_record.signal_count)
        )
        signal_counts_ok = (
            daily_record is not None
            and runtime_signal_count
            == integrity_signal_count
            == daily_summary_signal_count
        )
        checks.append(
            FullDayValidationCheck(
                key="signal_count_reconciliation",
                label="Signal count reconciliation",
                passed=signal_counts_ok,
                message=(
                    "runtime="
                    f"{runtime_signal_count}, "
                    "integrity="
                    f"{integrity_signal_count}, "
                    "daily_summary="
                    f"{daily_summary_signal_count}"
                ),
            )
        )

        runtime_pnl = self._preferred_runtime_pnl(
            runtime
        )
        daily_summary_pnl = (
            None
            if daily_record is None
            else self._float_or_none(
                daily_record.net_profit_loss
            )
        )
        report_summary = daily_report.get("summary")
        if not isinstance(report_summary, dict):
            report_summary = {}
        daily_report_pnl = self._float_or_none(
            report_summary.get("net_profit_loss")
        )

        pnl_sources_ok = self._numbers_match(
            runtime_pnl,
            daily_summary_pnl,
            daily_report_pnl,
        )
        checks.append(
            FullDayValidationCheck(
                key="pnl_source_reconciliation",
                label="P/L source reconciliation",
                passed=pnl_sources_ok,
                message=(
                    "runtime="
                    f"{runtime_pnl}, "
                    "daily_summary="
                    f"{daily_summary_pnl}, "
                    "daily_report="
                    f"{daily_report_pnl}"
                ),
            )
        )

        trade_count = self._integer(
            report_summary.get("trade_count")
        )
        completed_trade_count_ok = (
            trade_count == 0
            or runtime_execution_count >= trade_count
        )
        checks.append(
            FullDayValidationCheck(
                key="completed_trade_plausibility",
                label="Completed-trade plausibility",
                passed=completed_trade_count_ok,
                message=(
                    f"completed_trades={trade_count}, "
                    f"executions={runtime_execution_count}"
                ),
            )
        )

        generated_at = self._current_time()
        passed = all(check.passed for check in checks)

        return FullDayValidationResult(
            generated_at=generated_at,
            trading_date=trading_date,
            passed=passed,
            checks=tuple(checks),
            runtime=self._summary_runtime(runtime),
            integrity=self._summary_integrity(integrity),
            daily_summary=daily_summary_payload,
            daily_report=self._summary_daily_report(
                daily_report
            ),
        )

    def _check_source_date(
        self,
        checks: list[FullDayValidationCheck],
        *,
        key: str,
        label: str,
        payload: dict[str, Any],
        expected: date,
    ) -> None:
        actual = str(
            payload.get("trading_date") or ""
        )
        passed = actual == expected.isoformat()
        checks.append(
            FullDayValidationCheck(
                key=key,
                label=label,
                passed=passed,
                message=(
                    f"expected={expected.isoformat()}, "
                    f"actual={actual or 'missing'}"
                ),
            )
        )

    def _check_report_date(
        self,
        checks: list[FullDayValidationCheck],
        *,
        payload: dict[str, Any],
        expected: date,
    ) -> None:
        actual = str(
            payload.get("report_date") or ""
        )
        checks.append(
            FullDayValidationCheck(
                key="daily_report_date",
                label="Daily report date",
                passed=actual == expected.isoformat(),
                message=(
                    f"expected={expected.isoformat()}, "
                    f"actual={actual or 'missing'}"
                ),
            )
        )

    def _numbers_match(
        self,
        *values: float | None,
    ) -> bool:
        if any(value is None for value in values):
            return False
        resolved = [
            float(value)
            for value in values
            if value is not None
        ]
        return (
            max(resolved) - min(resolved)
            <= self.pnl_tolerance
        )

    @staticmethod
    def _preferred_runtime_pnl(
        runtime: dict[str, Any],
    ) -> float | None:
        for key in (
            "realized_profit_loss",
            "session_equity_change",
            "net_profit_loss",
        ):
            value = FullDayValidationService._float_or_none(
                runtime.get(key)
            )
            if value is not None:
                return value
        return None

    @staticmethod
    def _summary_runtime(
        runtime: dict[str, Any],
    ) -> dict[str, object]:
        keys = (
            "state",
            "cycle_count",
            "successful_cycle_count",
            "failed_cycle_count",
            "signal_count",
            "execution_count",
            "cycle_execution_count",
            "external_execution_count",
            "open_position_count",
            "portfolio_position_count",
            "realized_profit_loss",
            "session_equity_change",
            "pnl_reconciliation_difference",
            "pnl_consistent",
            "risk_evaluated_cycle_count",
            "risk_blocked_cycle_count",
            "error_message",
        )
        return {
            key: runtime.get(key)
            for key in keys
        }

    @staticmethod
    def _summary_integrity(
        integrity: dict[str, Any],
    ) -> dict[str, object]:
        keys = (
            "integrity_ok",
            "trace_available",
            "selected_count",
            "loaded_count",
            "monitored_count",
            "signal_count",
            "execution_count",
            "selected_not_loaded_codes",
            "loaded_not_monitored_codes",
            "monitored_not_loaded_codes",
            "orphan_signal_codes",
            "orphan_execution_codes",
        )
        return {
            key: integrity.get(key)
            for key in keys
        }

    @staticmethod
    def _summary_daily_report(
        report: dict[str, Any],
    ) -> dict[str, object]:
        summary = report.get("summary")
        if not isinstance(summary, dict):
            summary = {}
        return {
            "status": report.get("status"),
            "trade_count": summary.get("trade_count"),
            "net_profit_loss": summary.get(
                "net_profit_loss"
            ),
            "error_count": report.get("error_count"),
            "recovery_count": report.get(
                "recovery_count"
            ),
        }

    @staticmethod
    def _daily_record_payload(
        record: PaperTradingDailyRecord | None,
    ) -> dict[str, object]:
        if record is None:
            return {
                "available": False,
            }
        return {
            "available": True,
            "status": getattr(
                record.status,
                "value",
                str(record.status),
            ),
            "cycle_count": record.cycle_count,
            "successful_cycle_count": (
                record.successful_cycle_count
            ),
            "failed_cycle_count": (
                record.failed_cycle_count
            ),
            "signal_count": record.signal_count,
            "execution_count": record.execution_count,
            "net_profit_loss": record.net_profit_loss,
            "error_message": record.error_message,
        }

    def _read_integrity_for_date(
        self,
        trading_date: date,
    ) -> dict[str, Any]:
        archived_path = (
            self.integrity_history_directory
            / f"{trading_date.isoformat()}.json"
        )
        archived = self._read_json(
            archived_path
        )
        if (
            str(archived.get("trading_date") or "")
            == trading_date.isoformat()
        ):
            return archived

        latest = self._read_json(
            self.integrity_report_path
        )
        if (
            str(latest.get("trading_date") or "")
            == trading_date.isoformat()
        ):
            return latest

        return {}

    @staticmethod
    def _read_json(
        path: Path,
    ) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            return {}
        return (
            payload
            if isinstance(payload, dict)
            else {}
        )

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _float_or_none(
        value: Any,
    ) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )
        return current.astimezone(timezone.utc)
