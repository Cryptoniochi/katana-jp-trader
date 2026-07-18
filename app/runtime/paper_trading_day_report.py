"""終日Paper Trading運用結果をJSON互換辞書へ変換する。"""

from __future__ import annotations

from typing import Any

from app.runtime.paper_trading_daily_report import (
    paper_trading_daily_summary_to_dict,
)
from app.runtime.paper_trading_day_models import (
    PaperTradingDayResult,
)


def paper_trading_day_result_to_dict(
    result: PaperTradingDayResult,
) -> dict[str, Any]:
    """終日運用結果を辞書へ変換する。"""

    return {
        "trading_date": result.trading_date.isoformat(),
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat(),
        "stop_reason": result.stop_reason.value,
        "error_message": result.error_message,
        "cycle_count": result.cycle_count,
        "net_profit_loss": result.net_profit_loss,
        "return_rate": result.return_rate,
        "summary": paper_trading_daily_summary_to_dict(
            result.summary
        ),
        "persistence": {
            "created_at": result.record.created_at.isoformat(),
            "updated_at": result.record.updated_at.isoformat(),
            "status": result.record.status.value,
        },
    }
