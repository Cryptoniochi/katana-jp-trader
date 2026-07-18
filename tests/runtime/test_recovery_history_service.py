"""RecoveryHistoryServiceのユニットテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.dashboard.recovery_summary import (
    RecoveryStatus as DashboardRecoveryStatus,
)
from app.runtime.recovery_history_models import (
    RecoveryComponent,
)
from app.runtime.recovery_history_repository import (
    RecoveryHistoryRepository,
)
from app.runtime.recovery_history_service import (
    RecoveryHistoryService,
)
from app.runtime.recovery_models import (
    RecoveryAttempt,
    RecoveryResult,
    RecoveryStatus,
)


def make_attempt(
    *,
    attempt_number: int,
    started_at: datetime,
    successful: bool,
) -> RecoveryAttempt:
    """テスト用RecoveryAttemptを生成する。"""

    return RecoveryAttempt(
        attempt_number=attempt_number,
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=1),
        successful=successful,
        error_message=None if successful else "failed",
        delay_seconds_before_attempt=0.0,
    )


def make_result(
    *,
    recovery_name: str,
    started_at: datetime,
    attempt_successes: tuple[bool, ...],
    status: RecoveryStatus,
) -> RecoveryResult:
    """テスト用RecoveryResultを生成する。"""

    attempts = tuple(
        make_attempt(
            attempt_number=index,
            started_at=started_at + timedelta(seconds=index - 1),
            successful=successful,
        )
        for index, successful in enumerate(
            attempt_successes,
            start=1,
        )
    )

    completed_at = (
        attempts[-1].completed_at
        if attempts
        else started_at
    )

    return RecoveryResult(
        recovery_name=recovery_name,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        attempts=attempts,
        message=(
            "aborted"
            if status is RecoveryStatus.ABORTED
            else None
        ),
    )


def test_record_saves_recovery_result() -> None:
    """RecoveryResultを履歴へ保存できる。"""

    repository = RecoveryHistoryRepository()
    service = RecoveryHistoryService(repository)
    started_at = datetime(
        2026,
        7,
        18,
        1,
        0,
        tzinfo=timezone.utc,
    )

    result = make_result(
        recovery_name="broker_reconnect",
        started_at=started_at,
        attempt_successes=(True,),
        status=RecoveryStatus.SUCCESS,
    )

    entry = service.record(
        component=RecoveryComponent.BROKER,
        result=result,
    )

    assert entry.component is RecoveryComponent.BROKER
    assert entry.result is result
    assert service.list_history() == (entry,)


def test_build_summary_returns_empty_healthy_summary() -> None:
    """履歴がない場合は正常な空サマリーを返す。"""

    repository = RecoveryHistoryRepository()
    service = RecoveryHistoryService(repository)
    generated_at = datetime(
        2026,
        7,
        18,
        2,
        0,
        tzinfo=timezone.utc,
    )

    summary = service.build_summary(
        generated_at=generated_at
    )

    assert summary.total_attempts == 0
    assert summary.total_successes == 0
    assert summary.total_failures == 0
    assert summary.recovery_status is (
        DashboardRecoveryStatus.NORMAL
    )
    assert summary.is_healthy() is True
    assert summary.generated_at == generated_at


def test_build_summary_aggregates_broker_and_runtime() -> None:
    """BrokerとRuntimeの履歴をそれぞれ集計する。"""

    repository = RecoveryHistoryRepository()
    service = RecoveryHistoryService(repository)
    base_time = datetime(
        2026,
        7,
        18,
        1,
        0,
        tzinfo=timezone.utc,
    )

    broker_result = make_result(
        recovery_name="broker_reconnect",
        started_at=base_time,
        attempt_successes=(False, True),
        status=RecoveryStatus.SUCCESS,
    )
    runtime_result = make_result(
        recovery_name="runtime_restart",
        started_at=base_time + timedelta(minutes=10),
        attempt_successes=(False, False),
        status=RecoveryStatus.FAILED,
    )

    service.record(
        component=RecoveryComponent.BROKER,
        result=broker_result,
    )
    service.record(
        component=RecoveryComponent.RUNTIME,
        result=runtime_result,
    )

    summary = service.build_summary(
        generated_at=base_time + timedelta(hours=1)
    )

    assert summary.broker_attempts == 2
    assert summary.broker_successes == 1
    assert summary.broker_failures == 1
    assert summary.last_broker_recovery == (
        broker_result.completed_at
    )

    assert summary.runtime_attempts == 2
    assert summary.runtime_successes == 0
    assert summary.runtime_failures == 2
    assert summary.last_runtime_recovery == (
        runtime_result.completed_at
    )

    assert summary.total_attempts == 4
    assert summary.total_successes == 1
    assert summary.total_failures == 3
    assert summary.success_rate() == 25.0
    assert summary.recovery_status is (
        DashboardRecoveryStatus.FAILED
    )


def test_latest_success_maps_to_normal_status() -> None:
    """最新の復旧結果がSUCCESSならNORMALになる。"""

    repository = RecoveryHistoryRepository()
    service = RecoveryHistoryService(repository)
    base_time = datetime(
        2026,
        7,
        18,
        1,
        0,
        tzinfo=timezone.utc,
    )

    failed_result = make_result(
        recovery_name="failed_runtime",
        started_at=base_time,
        attempt_successes=(False,),
        status=RecoveryStatus.FAILED,
    )
    successful_result = make_result(
        recovery_name="broker_reconnect",
        started_at=base_time + timedelta(minutes=10),
        attempt_successes=(True,),
        status=RecoveryStatus.SUCCESS,
    )

    service.record(
        component=RecoveryComponent.RUNTIME,
        result=failed_result,
    )
    service.record(
        component=RecoveryComponent.BROKER,
        result=successful_result,
    )

    summary = service.build_summary()

    assert summary.recovery_status is (
        DashboardRecoveryStatus.NORMAL
    )
    assert summary.has_failure() is True
    assert summary.is_healthy() is False


def test_latest_retrying_maps_to_recovering_status() -> None:
    """最新結果がRETRYINGならRECOVERINGになる。"""

    repository = RecoveryHistoryRepository()
    service = RecoveryHistoryService(repository)
    started_at = datetime(
        2026,
        7,
        18,
        1,
        0,
        tzinfo=timezone.utc,
    )

    retrying_result = make_result(
        recovery_name="runtime_retry",
        started_at=started_at,
        attempt_successes=(),
        status=RecoveryStatus.RETRYING,
    )

    service.record(
        component=RecoveryComponent.RUNTIME,
        result=retrying_result,
    )

    summary = service.build_summary()

    assert summary.recovery_status is (
        DashboardRecoveryStatus.RECOVERING
    )


def test_latest_aborted_maps_to_failed_status() -> None:
    """最新結果がABORTEDならFAILEDになる。"""

    repository = RecoveryHistoryRepository()
    service = RecoveryHistoryService(repository)
    started_at = datetime(
        2026,
        7,
        18,
        1,
        0,
        tzinfo=timezone.utc,
    )

    aborted_result = make_result(
        recovery_name="runtime_abort",
        started_at=started_at,
        attempt_successes=(),
        status=RecoveryStatus.ABORTED,
    )

    service.record(
        component=RecoveryComponent.RUNTIME,
        result=aborted_result,
    )

    summary = service.build_summary()

    assert summary.recovery_status is (
        DashboardRecoveryStatus.FAILED
    )


def test_build_summary_rejects_naive_generated_at() -> None:
    """timezone情報のない生成日時を拒否する。"""

    repository = RecoveryHistoryRepository()
    service = RecoveryHistoryService(repository)

    with pytest.raises(
        ValueError,
        match="generated_at must be timezone-aware",
    ):
        service.build_summary(
            generated_at=datetime(2026, 7, 18, 9, 0)
        )


def test_service_rejects_invalid_repository() -> None:
    """不正なRepositoryを拒否する。"""

    with pytest.raises(
        TypeError,
        match=(
            "repository must be a "
            "RecoveryHistoryRepository"
        ),
    ):
        RecoveryHistoryService(  # type: ignore[arg-type]
            repository="invalid"
        )