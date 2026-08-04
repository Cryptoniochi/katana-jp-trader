"""Paper Trading Runtime状態JSONをDashboard向けに読み込む。"""

from __future__ import annotations

import json
from pathlib import Path


DEFAULT_RUNTIME_STATUS_PATH = Path(
    "reports/service/paper_trading_runtime_status.json"
)


class PaperTradingRuntimeStatusReader:
    """Runtime状態ファイルを安全に読み込む。"""

    def __init__(
        self,
        status_path: Path = DEFAULT_RUNTIME_STATUS_PATH,
    ) -> None:
        self.status_path = Path(status_path)

    def read(self) -> dict[str, object]:
        if not self.status_path.exists():
            return self.empty_payload(
                "Paper Trading Runtime has not reported yet."
            )

        try:
            payload = json.loads(
                self.status_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ) as error:
            return self.empty_payload(
                "Paper Trading Runtime status could not be read. "
                f"error={type(error).__name__}: {error}"
            )

        if not isinstance(payload, dict):
            return self.empty_payload(
                "Paper Trading Runtime status is invalid."
            )

        normalized = self.empty_payload(None)
        normalized.update(payload)
        normalized["available"] = True
        return normalized

    @staticmethod
    def empty_payload(
        message: str | None,
    ) -> dict[str, object]:
        return {
            "available": False,
            "generated_at": None,
            "trading_date": None,
            "state": "not_reported",
            "process_id": None,
            "started_at": None,
            "last_cycle_at": None,
            "cycle_count": 0,
            "successful_cycle_count": 0,
            "failed_cycle_count": 0,
            "signal_count": 0,
            "execution_count": 0,
            "open_position_count": 0,
            "portfolio_position_count": 0,
            "initial_equity": None,
            "current_equity": None,
            "net_profit_loss": None,
            "session_equity_change": None,
            "realized_profit_loss": None,
            "unrealized_profit_loss": None,
            "total_portfolio_profit_loss": None,
            "risk_evaluated_cycle_count": 0,
            "risk_blocked_cycle_count": 0,
            "error_message": None,
            "message": message,
        }
