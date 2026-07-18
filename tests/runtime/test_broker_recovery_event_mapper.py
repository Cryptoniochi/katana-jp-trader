"""Tests for Broker RecoveryEvent mapper."""

from datetime import datetime, timedelta, timezone

import pytest

from app.runtime.broker_recovery_event_mapper import (
    map_broker_recovery_result,
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
    13,
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
    recovery_name: str = "fake reconnect",
    status: RecoveryStatus = RecoveryStatus.SUCCESS,
    attempts: tuple[RecoveryAttempt, ...] | None = None,
    message: str | None = None,
) -> RecoveryResult:
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


def test_maps_success_result_to_broker_event() -> None:
    event = map_broker_recovery_result(
        make_result()
    )

    assert event.source is RecoverySource.BROKER
    assert (
        event.category
        is RecoveryEventCategory.RECONNECT
    )
    assert (
        event.status
        is RecoveryEventStatus.SUCCEEDED
    )
    assert event.name == "fake reconnect"
    assert event.started_at == STARTED_AT
    assert event.completed_at == COMPLETED_AT
    assert event.message is None
    assert event.succeeded is True


def test_accepts_explicit_event_category() -> None:
    event = map_broker_recovery_result(
        make_result(),
        category=RecoveryEventCategory.RECOVERY,
    )

    assert (
        event.category
        is RecoveryEventCategory.RECOVERY
    )


def test_maps_retrying_result_without_completed_at() -> None:
    failed_attempt = make_attempt(
        successful=False,
        error_message="temporary broker error",
    )
    result = make_result(
        status=RecoveryStatus.RETRYING,
        attempts=(failed_attempt,),
        message="retrying broker recovery",
    )

    event = map_broker_recovery_result(result)

    assert (
        event.status
        is RecoveryEventStatus.RETRYING
    )
    assert event.completed_at is None
    assert event.is_terminal is False
    assert event.message == "retrying broker recovery"
    assert (
        event.metadata["observed_at"]
        == COMPLETED_AT.isoformat()
    )


def test_maps_failed_result_to_failed_event() -> None:
    failed_attempt = make_attempt(
        successful=False,
        error_message="reconnect failed",
    )
    result = make_result(
        status=RecoveryStatus.FAILED,
        attempts=(failed_attempt,),
        message="broker could not recover",
    )

    event = map_broker_recovery_result(result)

    assert (
        event.status
        is RecoveryEventStatus.FAILED
    )
    assert event.completed_at == COMPLETED_AT
    assert event.message == "broker could not recover"
    assert event.failed is True


def test_failed_result_uses_last_attempt_error() -> None:
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

    event = map_broker_recovery_result(result)

    assert event.message == "final error"


def test_maps_aborted_result_to_aborted_event() -> None:
    result = make_result(
        status=RecoveryStatus.ABORTED,
        attempts=(),
        message="shutdown was requested",
    )

    event = map_broker_recovery_result(result)

    assert (
        event.status
        is RecoveryEventStatus.ABORTED
    )
    assert event.message == "shutdown was requested"
    assert event.completed_at == COMPLETED_AT
    assert event.failed is True


def test_maps_attempt_counts_to_metadata() -> None:
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

    event = map_broker_recovery_result(result)

    assert event.metadata["attempt_count"] == 2
    assert event.metadata["success_count"] == 1
    assert event.metadata["failure_count"] == 1
    assert (
        event.metadata["total_delay_seconds"]
        == pytest.approx(2.0)
    )


def test_maps_attempt_details_to_metadata() -> None:
    attempt = make_attempt(
        successful=False,
        error_message="connection error",
        delay_seconds_before_attempt=1.5,
    )
    result = make_result(
        status=RecoveryStatus.FAILED,
        attempts=(attempt,),
    )

    event = map_broker_recovery_result(result)
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


def test_metadata_keeps_original_broker_status() -> None:
    event = map_broker_recovery_result(
        make_result()
    )

    assert (
        event.metadata["broker_status"]
        == RecoveryStatus.SUCCESS.value
    )


def test_mapper_rejects_invalid_result_type() -> None:
    with pytest.raises(
        TypeError,
        match="result must be a RecoveryResult",
    ):
        map_broker_recovery_result("invalid")


def test_mapper_rejects_invalid_category_type() -> None:
    with pytest.raises(
        TypeError,
        match=(
            "category must be a RecoveryEventCategory"
        ),
    ):
        map_broker_recovery_result(
            make_result(),
            category="reconnect",
        )
