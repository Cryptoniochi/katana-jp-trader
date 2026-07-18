"""Runtime RecoveryEvent Mapperのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.runtime.recovery_event_mapper import (
    map_runtime_recovery_result,
)
from app.runtime.recovery_event_models import (
    RecoveryEventCategory,
    RecoveryEventStatus,
    RecoverySource,
)
from app.runtime.recovery_models import (
    RecoveryAttempt,
    RecoveryResult,
    RecoveryStatus,
)


STARTED_AT = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)

FIRST_COMPLETED_AT = (
    STARTED_AT + timedelta(seconds=1)
)

SECOND_STARTED_AT = (
    STARTED_AT + timedelta(seconds=2)
)

COMPLETED_AT = (
    STARTED_AT + timedelta(seconds=4)
)


def make_attempt(
    *,
    attempt_number: int = 1,
    started_at: datetime = STARTED_AT,
    completed_at: datetime = FIRST_COMPLETED_AT,
    successful: bool = True,
    error_message: str | None = None,
    delay_seconds_before_attempt: float = 0.0,
) -> RecoveryAttempt:
    """テスト用RecoveryAttemptを生成する。"""

    return RecoveryAttempt(
        attempt_number=attempt_number,
        started_at=started_at,
        completed_at=completed_at,
        successful=successful,
        error_message=error_message,
        delay_seconds_before_attempt=(
            delay_seconds_before_attempt
        ),
    )


def make_result(
    *,
    recovery_name: str = "runtime restart",
    status: RecoveryStatus = RecoveryStatus.SUCCESS,
    attempts: tuple[RecoveryAttempt, ...] | None = None,
    message: str | None = None,
) -> RecoveryResult:
    """テスト用RecoveryResultを生成する。"""

    if attempts is None:
        attempts = (
            make_attempt(),
        )

    return RecoveryResult(
        recovery_name=recovery_name,
        status=status,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        attempts=attempts,
        message=message,
    )


def test_maps_success_result_to_succeeded_event() -> None:
    """SUCCESSをSUCCEEDEDイベントへ変換する。"""

    result = make_result()

    event = map_runtime_recovery_result(result)

    assert event.source is RecoverySource.RUNTIME
    assert (
        event.category
        is RecoveryEventCategory.RECOVERY
    )
    assert (
        event.status
        is RecoveryEventStatus.SUCCEEDED
    )
    assert event.name == "runtime restart"
    assert event.started_at == STARTED_AT
    assert event.completed_at == COMPLETED_AT
    assert event.message is None
    assert event.succeeded is True


def test_accepts_explicit_event_category() -> None:
    """明示されたEvent分類を使用する。"""

    event = map_runtime_recovery_result(
        make_result(),
        category=RecoveryEventCategory.RESTART,
    )

    assert (
        event.category
        is RecoveryEventCategory.RESTART
    )


def test_maps_retrying_result_without_completed_at() -> None:
    """RETRYINGを進行中イベントとして変換する。"""

    failed_attempt = make_attempt(
        successful=False,
        error_message="temporary broker error",
    )
    result = make_result(
        status=RecoveryStatus.RETRYING,
        attempts=(failed_attempt,),
        message="retrying recovery",
    )

    event = map_runtime_recovery_result(result)

    assert (
        event.status
        is RecoveryEventStatus.RETRYING
    )
    assert event.completed_at is None
    assert event.is_terminal is False
    assert event.message == "retrying recovery"
    assert (
        event.metadata["observed_at"]
        == COMPLETED_AT.isoformat()
    )


def test_maps_failed_result_to_failed_event() -> None:
    """FAILEDをFAILEDイベントへ変換する。"""

    failed_attempt = make_attempt(
        successful=False,
        error_message="restart failed",
    )
    result = make_result(
        status=RecoveryStatus.FAILED,
        attempts=(failed_attempt,),
        message="runtime could not recover",
    )

    event = map_runtime_recovery_result(result)

    assert (
        event.status
        is RecoveryEventStatus.FAILED
    )
    assert event.completed_at == COMPLETED_AT
    assert event.message == "runtime could not recover"
    assert event.failed is True


def test_failed_result_uses_last_attempt_error() -> None:
    """Resultメッセージがない場合は最終試行エラーを使用する。"""

    first_attempt = make_attempt(
        attempt_number=1,
        successful=False,
        error_message="first error",
    )
    second_attempt = make_attempt(
        attempt_number=2,
        started_at=SECOND_STARTED_AT,
        completed_at=COMPLETED_AT,
        successful=False,
        error_message="final error",
        delay_seconds_before_attempt=1.0,
    )
    result = make_result(
        status=RecoveryStatus.FAILED,
        attempts=(
            first_attempt,
            second_attempt,
        ),
    )

    event = map_runtime_recovery_result(result)

    assert event.message == "final error"


def test_maps_aborted_result_to_aborted_event() -> None:
    """ABORTEDをABORTEDイベントへ変換する。"""

    result = make_result(
        status=RecoveryStatus.ABORTED,
        attempts=(),
        message="shutdown was requested",
    )

    event = map_runtime_recovery_result(result)

    assert (
        event.status
        is RecoveryEventStatus.ABORTED
    )
    assert event.message == "shutdown was requested"
    assert event.completed_at == COMPLETED_AT
    assert event.failed is True


def test_maps_attempt_counts_to_metadata() -> None:
    """試行件数をMetadataへ格納する。"""

    first_attempt = make_attempt(
        attempt_number=1,
        successful=False,
        error_message="temporary error",
    )
    second_attempt = make_attempt(
        attempt_number=2,
        started_at=SECOND_STARTED_AT,
        completed_at=COMPLETED_AT,
        successful=True,
        delay_seconds_before_attempt=2.0,
    )
    result = make_result(
        attempts=(
            first_attempt,
            second_attempt,
        ),
    )

    event = map_runtime_recovery_result(result)

    assert event.metadata["attempt_count"] == 2
    assert event.metadata["success_count"] == 1
    assert event.metadata["failure_count"] == 1
    assert (
        event.metadata["total_delay_seconds"]
        == pytest.approx(2.0)
    )


def test_maps_attempt_details_to_metadata() -> None:
    """試行詳細をMetadataへ格納する。"""

    attempt = make_attempt(
        successful=False,
        error_message="connection error",
        delay_seconds_before_attempt=1.5,
    )
    result = make_result(
        status=RecoveryStatus.FAILED,
        attempts=(attempt,),
    )

    event = map_runtime_recovery_result(result)
    attempts = event.metadata["attempts"]

    assert isinstance(attempts, tuple)
    assert len(attempts) == 1

    attempt_data = attempts[0]

    assert attempt_data == {
        "attempt_number": 1,
        "started_at": STARTED_AT.isoformat(),
        "completed_at": (
            FIRST_COMPLETED_AT.isoformat()
        ),
        "successful": False,
        "error_message": "connection error",
        "delay_seconds_before_attempt": 1.5,
        "duration_seconds": 1.0,
    }


def test_metadata_keeps_original_runtime_status() -> None:
    """元のRuntime状態をMetadataへ保持する。"""

    result = make_result()

    event = map_runtime_recovery_result(result)

    assert (
        event.metadata["runtime_status"]
        == RecoveryStatus.SUCCESS.value
    )


def test_mapper_rejects_invalid_result_type() -> None:
    """RecoveryResult以外を拒否する。"""

    with pytest.raises(
        TypeError,
        match="result must be a RecoveryResult",
    ):
        map_runtime_recovery_result("invalid")


def test_mapper_rejects_invalid_category_type() -> None:
    """RecoveryEventCategory以外を拒否する。"""

    with pytest.raises(
        TypeError,
        match=(
            "category must be a RecoveryEventCategory"
        ),
    ):
        map_runtime_recovery_result(
            make_result(),
            category="restart",
        )