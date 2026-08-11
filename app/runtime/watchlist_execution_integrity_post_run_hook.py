"""Watchlist-to-Execution Integrity AuditのPaper Trading終了後Hook。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from app.runtime.paper_trading_day_models import (
    PaperTradingDayResult,
)
from app.runtime.watchlist_execution_integrity_service import (
    WatchlistExecutionIntegrityResult,
)


class WatchlistExecutionIntegrityAuditor(Protocol):
    """日次Watchlist-to-Execution監査を実行する。"""

    def audit(
        self,
        *,
        trading_date,
    ) -> WatchlistExecutionIntegrityResult:
        """指定営業日の整合性を監査する。"""


class WatchlistExecutionIntegrityPostRunHook:
    """Paper Trading終了後にIntegrity Auditを実行・保存する。"""

    def __init__(
        self,
        *,
        audit_service: WatchlistExecutionIntegrityAuditor,
        report_path: Path = Path(
            "reports/service/"
            "watchlist_execution_integrity.json"
        ),
        history_directory: Path = Path(
            "reports/service/"
            "watchlist_execution_integrity_history"
        ),
    ) -> None:
        self.audit_service = audit_service
        self.report_path = Path(report_path)
        self.history_directory = Path(
            history_directory
        )

    def handle(
        self,
        result: PaperTradingDayResult,
    ) -> None:
        """終了した営業日を監査し、最新結果を原子的に保存する。"""

        audit_result = self.audit_service.audit(
            trading_date=result.trading_date
        )
        self._write_report(
            self.report_path,
            audit_result,
        )
        self._write_report(
            self.history_directory
            / f"{result.trading_date.isoformat()}.json",
            audit_result,
        )

    @staticmethod
    def _write_report(
        path: Path,
        result: WatchlistExecutionIntegrityResult,
    ) -> None:
        path = Path(path)
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        temporary = path.with_suffix(
            path.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(
                result.to_dict(),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(path)
