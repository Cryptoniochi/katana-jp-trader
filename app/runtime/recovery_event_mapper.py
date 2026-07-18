"""Runtime RecoveryResultを共通RecoveryEventへ変換する。"""

from __future__ import annotations

from app.runtime.recovery_event_models import (
    RecoveryEvent,
    RecoveryEventCategory,
    RecoveryEventStatus,
    RecoverySource,
)
from app.runtime.recovery_models import (
    RecoveryAttempt,
    RecoveryResult,
    RecoveryStatus,
)


_RUNTIME_STATUS_MAPPING = {
    RecoveryStatus.SUCCESS: RecoveryEventStatus.SUCCEEDED,
    RecoveryStatus.RETRYING: RecoveryEventStatus.RETRYING,
    RecoveryStatus.FAILED: RecoveryEventStatus.FAILED,
    RecoveryStatus.ABORTED: RecoveryEventStatus.ABORTED,
}


def map_runtime_recovery_result(
    result: RecoveryResult,
    *,
    category: RecoveryEventCategory = (
        RecoveryEventCategory.RECOVERY
    ),
) -> RecoveryEvent:
    """Runtime RecoveryResultを共通RecoveryEventへ変換する。"""

    if not isinstance(result, RecoveryResult):
        raise TypeError(
            "result must be a RecoveryResult"
        )

    if not isinstance(
        category,
        RecoveryEventCategory,
    ):
        raise TypeError(
            "category must be a RecoveryEventCategory"
        )

    event_status = _RUNTIME_STATUS_MAPPING[
        result.status
    ]

    completed_at = (
        None
        if event_status
        in {
            RecoveryEventStatus.STARTED,
            RecoveryEventStatus.RETRYING,
        }
        else result.completed_at
    )

    message = _resolve_event_message(
        result=result,
        event_status=event_status,
    )

    metadata: dict[str, object] = {
        "runtime_status": result.status.value,
        "attempt_count": result.attempt_count,
        "success_count": sum(
            attempt.successful
            for attempt in result.attempts
        ),
        "failure_count": sum(
            not attempt.successful
            for attempt in result.attempts
        ),
        "total_delay_seconds": (
            result.total_delay_seconds
        ),
        "attempts": tuple(
            _attempt_metadata(attempt)
            for attempt in result.attempts
        ),
    }

    if result.status is RecoveryStatus.RETRYING:
        metadata["observed_at"] = (
            result.completed_at.isoformat()
        )

    return RecoveryEvent(
        source=RecoverySource.RUNTIME,
        category=category,
        status=event_status,
        name=result.recovery_name,
        started_at=result.started_at,
        completed_at=completed_at,
        message=message,
        metadata=metadata,
    )


def _resolve_event_message(
    *,
    result: RecoveryResult,
    event_status: RecoveryEventStatus,
) -> str | None:
    """Event状態に適したメッセージを返す。"""

    if result.message is not None:
        return result.message

    if event_status not in {
        RecoveryEventStatus.FAILED,
        RecoveryEventStatus.ABORTED,
    }:
        return None

    for attempt in reversed(result.attempts):
        if attempt.error_message is not None:
            return attempt.error_message

    if event_status is RecoveryEventStatus.ABORTED:
        return "Runtime recovery was aborted."

    return "Runtime recovery failed."


def _attempt_metadata(
    attempt: RecoveryAttempt,
) -> dict[str, object]:
    """1回分のRecovery試行をMetadata形式へ変換する。"""

    return {
        "attempt_number": attempt.attempt_number,
        "started_at": attempt.started_at.isoformat(),
        "completed_at": attempt.completed_at.isoformat(),
        "successful": attempt.successful,
        "error_message": attempt.error_message,
        "delay_seconds_before_attempt": (
            attempt.delay_seconds_before_attempt
        ),
        "duration_seconds": (
            attempt.duration_seconds
        ),
    }