"""RecoveryResultをJSON互換辞書へ変換する。"""

from __future__ import annotations

from typing import Any

from app.runtime.recovery_models import RecoveryResult


def recovery_result_to_dict(
    result: RecoveryResult,
) -> dict[str, Any]:
    """復旧結果を辞書へ変換する。"""

    return {
        "recovery_name": result.recovery_name,
        "status": result.status.value,
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat(),
        "attempt_count": result.attempt_count,
        "succeeded": result.succeeded,
        "total_delay_seconds": result.total_delay_seconds,
        "message": result.message,
        "attempts": [
            {
                "attempt_number": attempt.attempt_number,
                "started_at": attempt.started_at.isoformat(),
                "completed_at": attempt.completed_at.isoformat(),
                "successful": attempt.successful,
                "error_message": attempt.error_message,
                "delay_seconds_before_attempt": (
                    attempt.delay_seconds_before_attempt
                ),
                "duration_seconds": attempt.duration_seconds,
            }
            for attempt in result.attempts
        ],
    }
