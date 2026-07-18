"""Paper Trading日次サマリーをJSON互換辞書へ変換する。"""

from __future__ import annotations

from typing import Any

from app.runtime.paper_trading_runtime_models import (
    PaperTradingDailySummary,
)


def paper_trading_daily_summary_to_dict(
    summary: PaperTradingDailySummary,
) -> dict[str, Any]:
    """日次サマリーを辞書へ変換する。"""

    return {
        "trading_date": summary.trading_date.isoformat(),
        "started_at": summary.started_at.isoformat(),
        "completed_at": summary.completed_at.isoformat(),
        "status": summary.status.value,
        "error_message": summary.error_message,
        "cycle_count": summary.cycle_count,
        "successful_cycle_count": (
            summary.successful_cycle_count
        ),
        "failed_cycle_count": (
            summary.failed_cycle_count
        ),
        "signal_count": summary.signal_count,
        "execution_count": summary.execution_count,
        "initial_equity": summary.initial_equity,
        "final_equity": summary.final_equity,
        "net_profit_loss": summary.net_profit_loss,
        "return_rate": summary.return_rate,
        "records": [
            {
                "cycle_number": record.cycle_number,
                "status": (
                    record.cycle_result.status.value
                ),
                "signal_count": (
                    record.cycle_result.signal_count
                ),
                "execution_count": (
                    record.cycle_result.execution_count
                ),
                "portfolio_equity": (
                    record.portfolio_snapshot.broker_equity
                    if record.portfolio_snapshot is not None
                    else None
                ),
                "error_message": (
                    record.cycle_result.error_message
                ),
            }
            for record in summary.records
        ],
    }
