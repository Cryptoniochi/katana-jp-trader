"""Backtest Runtime結果をJSON互換辞書へ変換する。"""

from __future__ import annotations

from typing import Any

from app.backtest.backtest_runtime_models import (
    BacktestRuntimeResult,
)


def backtest_runtime_result_to_dict(
    result: BacktestRuntimeResult,
) -> dict[str, Any]:
    """Backtest Runtime結果を辞書へ変換する。"""

    metrics = result.metrics
    equity_curve = (
        result.run_result.equity_curve_report
        if result.run_result is not None
        else None
    )

    return {
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat(),
        "elapsed_seconds": result.elapsed_seconds,
        "status": result.status.value,
        "error_message": result.error_message,
        "frame_count": result.frame_count,
        "signal_count": result.signal_count,
        "order_count": result.order_count,
        "execution_count": result.execution_count,
        "metrics": (
            {
                "trade_count": metrics.trade_count,
                "winning_trade_count": (
                    metrics.winning_trade_count
                ),
                "losing_trade_count": (
                    metrics.losing_trade_count
                ),
                "flat_trade_count": (
                    metrics.flat_trade_count
                ),
                "gross_profit": metrics.gross_profit,
                "gross_loss": metrics.gross_loss,
                "net_profit_loss": (
                    metrics.net_profit_loss
                ),
                "win_rate": metrics.win_rate,
                "profit_factor": metrics.profit_factor,
                "expectancy": metrics.expectancy,
                "maximum_consecutive_wins": (
                    metrics.maximum_consecutive_wins
                ),
                "maximum_consecutive_losses": (
                    metrics.maximum_consecutive_losses
                ),
            }
            if metrics is not None
            else None
        ),
        "equity_curve": (
            {
                "initial_equity": (
                    equity_curve.initial_equity
                ),
                "final_equity": (
                    equity_curve.final_equity
                ),
                "absolute_profit_loss": (
                    equity_curve.absolute_profit_loss
                ),
                "total_return": (
                    equity_curve.total_return
                ),
                "maximum_drawdown": (
                    equity_curve.maximum_drawdown
                ),
                "maximum_drawdown_amount": (
                    equity_curve.maximum_drawdown_amount
                ),
            }
            if equity_curve is not None
            else None
        ),
    }
