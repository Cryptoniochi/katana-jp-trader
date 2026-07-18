"""Burn-in耐久試験結果をJSON互換辞書へ変換する。"""

from __future__ import annotations

from typing import Any

from app.runtime.burn_in_models import BurnInResult


def burn_in_result_to_dict(
    result: BurnInResult,
) -> dict[str, Any]:
    """Burn-in最終結果を辞書へ変換する。"""

    return {
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat(),
        "elapsed_seconds": result.elapsed_seconds,
        "stop_reason": result.stop_reason.value,
        "error_message": result.error_message,
        "cycle_count": result.cycle_count,
        "successful_cycle_count": (
            result.successful_cycle_count
        ),
        "failed_cycle_count": (
            result.failed_cycle_count
        ),
        "average_cycle_seconds": (
            result.average_cycle_seconds
        ),
        "minimum_cycle_seconds": (
            result.minimum_cycle_seconds
        ),
        "maximum_cycle_seconds": (
            result.maximum_cycle_seconds
        ),
        "maximum_consecutive_failures": (
            result.maximum_consecutive_failures
        ),
        "samples": [
            {
                "cycle_number": (
                    sample.cycle_result.cycle_number
                ),
                "status": (
                    sample.cycle_result.status.value
                ),
                "duration_seconds": (
                    sample.duration_seconds
                ),
                "consecutive_failure_count": (
                    sample.consecutive_failure_count
                ),
                "signal_count": (
                    sample.cycle_result.signal_count
                ),
                "execution_count": (
                    sample.cycle_result.execution_count
                ),
                "error_message": (
                    sample.cycle_result.error_message
                ),
            }
            for sample in result.samples
        ],
    }
