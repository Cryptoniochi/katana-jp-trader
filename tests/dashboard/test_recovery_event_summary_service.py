"""RecoveryEventSummaryServiceのユニットテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.dashboard.recovery_event_summary_service import (
    RecoveryEventSummaryService,
)
from app.dashboard.recovery_summary import (
    RecoveryStatus as DashboardRecoveryStatus,
)
from app.runtime.recovery_event_models import (
    RecoveryEvent,
    RecoveryEventCategory,
    RecoveryEventStatus,
    RecoverySource,
)
from app.runtime.recovery_event_repository import (
    RecoveryEventRepository,
)
from app.runtime.sqlite_recovery_event_repository import (
    SQLiteRecoveryEventRepository,
)


BASE_TIME = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


def make_event(
    *,
    event_id: str,
    source: RecoverySource,
    status: RecoveryEventStatus,
    started_at: datetime = BASE_TIME,
    completed_at: datetime | None = (
        BASE_TIME + timedelta(seconds=1)
    ),
    attempt_count: int | None = None,
    success_count: int | None = None,
    failure_count: int | None = None,
    message: str | None = None,
) -> RecoveryEvent:
    """テスト用RecoveryEventを生成する。"""

    if status in {
        RecoveryEventStatus.STARTED,
        RecoveryEventStatus.RETRYING,
    }:
        completed_at = None

    if status in {
        RecoveryEventStatus.FAILED,
        RecoveryEventStatus.ABORTED,
    } and message is None:
        message = "recovery failed"

    metadata: dict[str, object] = {}

    if attempt_count is not None:
        metadata["attempt_count"] = attempt_count

    if success_count is not None:
        metadata["success_count"] = success_count

    if failure_count is not None:
        metadata["failure_count"] = failure_count

    return RecoveryEvent(
        event_id=event_id,
        source=source,
        category=RecoveryEventCategory.RECOVERY,
        status=status,
        name=f"{source.value} recovery",
        started_at=started_at,
        completed_at=completed_at,
        message=message,
        metadata=metadata,
    )


def test_build_summary_returns_empty_normal_summary() -> None:
    """Eventがない場合は正常な空サマリーを返す。"""

    service = RecoveryEventSummaryService(
        RecoveryEventRepository()
    )
    generated_at = BASE_TIME + timedelta(hours=1)

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
    """BrokerとRuntimeをそれぞれ集計する。"""

    repository = RecoveryEventRepository()
    service = RecoveryEventSummaryService(repository)

    broker_event = make_event(
        event_id="broker-event",
        source=RecoverySource.BROKER,
        status=RecoveryEventStatus.SUCCEEDED,
        attempt_count=2,
        success_count=1,
        failure_count=1,
    )
    runtime_event = make_event(
        event_id="runtime-event",
        source=RecoverySource.RUNTIME,
        status=RecoveryEventStatus.FAILED,
        started_at=BASE_TIME + timedelta(minutes=10),
        completed_at=BASE_TIME + timedelta(
            minutes=10,
            seconds=2,
        ),
        attempt_count=2,
        success_count=0,
        failure_count=2,
    )

    repository.add(broker_event)
    repository.add(runtime_event)

    summary = service.build_summary(
        generated_at=BASE_TIME + timedelta(hours=1)
    )

    assert summary.broker_attempts == 2
    assert summary.broker_successes == 1
    assert summary.broker_failures == 1
    assert summary.last_broker_recovery == (
        broker_event.completed_at
    )

    assert summary.runtime_attempts == 2
    assert summary.runtime_successes == 0
    assert summary.runtime_failures == 2
    assert summary.last_runtime_recovery == (
        runtime_event.completed_at
    )

    assert summary.total_attempts == 4
    assert summary.total_successes == 1
    assert summary.total_failures == 3
    assert summary.success_rate() == 25.0
    assert summary.recovery_status is (
        DashboardRecoveryStatus.FAILED
    )


def test_latest_success_maps_to_normal() -> None:
    """最新Eventが成功ならDashboard状態はNORMALになる。"""

    repository = RecoveryEventRepository()
    service = RecoveryEventSummaryService(repository)

    repository.add(
        make_event(
            event_id="failed",
            source=RecoverySource.RUNTIME,
            status=RecoveryEventStatus.FAILED,
            attempt_count=1,
            success_count=0,
            failure_count=1,
        )
    )
    repository.add(
        make_event(
            event_id="success",
            source=RecoverySource.BROKER,
            status=RecoveryEventStatus.SUCCEEDED,
            started_at=BASE_TIME + timedelta(minutes=1),
            completed_at=BASE_TIME + timedelta(
                minutes=1,
                seconds=1,
            ),
            attempt_count=1,
            success_count=1,
            failure_count=0,
        )
    )

    summary = service.build_summary()

    assert summary.recovery_status is (
        DashboardRecoveryStatus.NORMAL
    )
    assert summary.has_failure() is True
    assert summary.is_healthy() is False


@pytest.mark.parametrize(
    "status",
    [
        RecoveryEventStatus.STARTED,
        RecoveryEventStatus.RETRYING,
    ],
)
def test_active_latest_event_maps_to_recovering(
    status: RecoveryEventStatus,
) -> None:
    """進行中の最新EventをRECOVERINGへ変換する。"""

    repository = RecoveryEventRepository()
    service = RecoveryEventSummaryService(repository)

    repository.add(
        make_event(
            event_id="active",
            source=RecoverySource.RUNTIME,
            status=status,
        )
    )

    summary = service.build_summary()

    assert summary.recovery_status is (
        DashboardRecoveryStatus.RECOVERING
    )


@pytest.mark.parametrize(
    "status",
    [
        RecoveryEventStatus.FAILED,
        RecoveryEventStatus.ABORTED,
    ],
)
def test_failed_latest_event_maps_to_failed(
    status: RecoveryEventStatus,
) -> None:
    """失敗・中断EventをFAILEDへ変換する。"""

    repository = RecoveryEventRepository()
    service = RecoveryEventSummaryService(repository)

    repository.add(
        make_event(
            event_id="failed",
            source=RecoverySource.RUNTIME,
            status=status,
            attempt_count=1,
            success_count=0,
            failure_count=1,
        )
    )

    summary = service.build_summary()

    assert summary.recovery_status is (
        DashboardRecoveryStatus.FAILED
    )


def test_event_without_metadata_uses_status_fallback() -> None:
    """件数Metadataがない場合はEvent状態から補完する。"""

    repository = RecoveryEventRepository()
    service = RecoveryEventSummaryService(repository)

    repository.add(
        make_event(
            event_id="success",
            source=RecoverySource.BROKER,
            status=RecoveryEventStatus.SUCCEEDED,
        )
    )
    repository.add(
        make_event(
            event_id="failure",
            source=RecoverySource.RUNTIME,
            status=RecoveryEventStatus.FAILED,
            started_at=BASE_TIME + timedelta(minutes=1),
            completed_at=BASE_TIME + timedelta(
                minutes=1,
                seconds=1,
            ),
        )
    )

    summary = service.build_summary()

    assert summary.broker_attempts == 1
    assert summary.broker_successes == 1
    assert summary.broker_failures == 0
    assert summary.runtime_attempts == 1
    assert summary.runtime_successes == 0
    assert summary.runtime_failures == 1


def test_live_and_supervisor_events_are_not_aggregated() -> None:
    """現行Summary対象外のEventは集計しない。"""

    repository = RecoveryEventRepository()
    service = RecoveryEventSummaryService(repository)

    repository.add(
        make_event(
            event_id="live",
            source=RecoverySource.LIVE,
            status=RecoveryEventStatus.FAILED,
        )
    )
    repository.add(
        make_event(
            event_id="supervisor",
            source=RecoverySource.SUPERVISOR,
            status=RecoveryEventStatus.FAILED,
            started_at=BASE_TIME + timedelta(minutes=1),
            completed_at=BASE_TIME + timedelta(
                minutes=1,
                seconds=1,
            ),
        )
    )

    summary = service.build_summary()

    assert summary.total_attempts == 0
    assert summary.total_successes == 0
    assert summary.total_failures == 0
    assert summary.recovery_status is (
        DashboardRecoveryStatus.NORMAL
    )


def test_summary_works_with_sqlite_repository(
    tmp_path,
) -> None:
    """SQLite保存済みEventからサマリーを生成できる。"""

    database_path = tmp_path / "katana.db"
    writer = SQLiteRecoveryEventRepository(
        database_path
    )

    event = make_event(
        event_id="runtime-event",
        source=RecoverySource.RUNTIME,
        status=RecoveryEventStatus.SUCCEEDED,
        attempt_count=2,
        success_count=1,
        failure_count=1,
    )
    writer.add(event)

    service = RecoveryEventSummaryService(
        SQLiteRecoveryEventRepository(
            database_path
        )
    )

    summary = service.build_summary()

    assert summary.runtime_attempts == 2
    assert summary.runtime_successes == 1
    assert summary.runtime_failures == 1
    assert summary.last_runtime_recovery == (
        event.completed_at
    )


def test_inconsistent_metadata_counts_are_rejected() -> None:
    """試行件数と成功・失敗件数の不一致を拒否する。"""

    repository = RecoveryEventRepository()
    service = RecoveryEventSummaryService(repository)

    repository.add(
        make_event(
            event_id="invalid-counts",
            source=RecoverySource.RUNTIME,
            status=RecoveryEventStatus.SUCCEEDED,
            attempt_count=2,
            success_count=1,
            failure_count=0,
        )
    )

    with pytest.raises(
        ValueError,
        match=(
            "RecoveryEvent attempt_count must equal "
            r"success_count \+ failure_count"
        ),
    ):
        service.build_summary()


def test_invalid_metadata_count_type_is_rejected() -> None:
    """件数Metadataの不正な型を拒否する。"""

    repository = RecoveryEventRepository()
    service = RecoveryEventSummaryService(repository)

    repository.add(
        RecoveryEvent(
            event_id="invalid-type",
            source=RecoverySource.RUNTIME,
            category=RecoveryEventCategory.RECOVERY,
            status=RecoveryEventStatus.SUCCEEDED,
            name="runtime recovery",
            started_at=BASE_TIME,
            completed_at=BASE_TIME + timedelta(seconds=1),
            metadata={
                "attempt_count": "one",
                "success_count": 1,
                "failure_count": 0,
            },
        )
    )

    with pytest.raises(
        TypeError,
        match=(
            "RecoveryEvent metadata attempt_count "
            "must be an int"
        ),
    ):
        service.build_summary()


def test_build_summary_rejects_naive_generated_at() -> None:
    """Timezoneなしの生成日時を拒否する。"""

    service = RecoveryEventSummaryService(
        RecoveryEventRepository()
    )

    with pytest.raises(
        ValueError,
        match="generated_at must be timezone-aware",
    ):
        service.build_summary(
            generated_at=datetime(
                2026,
                7,
                18,
                12,
                0,
            )
        )


def test_service_rejects_invalid_repository() -> None:
    """RecoveryEventRepository以外を拒否する。"""

    with pytest.raises(
        TypeError,
        match=(
            "repository must be a "
            "RecoveryEventRepository"
        ),
    ):
        RecoveryEventSummaryService(
            repository="invalid"
        )