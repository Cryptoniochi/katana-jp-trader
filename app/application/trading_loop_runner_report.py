"""Trading Loop Runner結果をJSON互換辞書へ変換する。"""

from __future__ import annotations

from typing import Any

from app.application.trading_loop_runner_models import (
    TradingLoopRunnerResult,
)


def trading_loop_runner_result_to_dict(
    result: TradingLoopRunnerResult,
) -> dict[str, Any]:
    """Trading Loop Runner結果を辞書へ変換する。"""

    return {
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat(),
        "stop_reason": result.stop_reason.value,
        "error_message": result.error_message,
        "cycle_count": result.cycle_count,
        "successful_cycle_count": (
            result.successful_cycle_count
        ),
        "failed_cycle_count": (
            result.failed_cycle_count
        ),
        "cycles": [
            {
                "cycle_number": cycle.cycle_number,
                "started_at": cycle.started_at.isoformat(),
                "completed_at": cycle.completed_at.isoformat(),
                "status": cycle.status.value,
                "signal_count": cycle.signal_count,
                "execution_count": cycle.execution_count,
                "error_message": cycle.error_message,
            }
            for cycle in result.cycles
        ],
    }
