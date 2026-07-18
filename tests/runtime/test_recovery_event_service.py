"""RecoveryEventServiceのユニットテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.runtime.recovery_event_models import (
    RecoveryEvent,
    RecoveryEventCategory,
    RecoveryEventStatus,
    RecoverySource,
)
from app.runtime.recovery_event_repository import (
    RecoveryEventRepository,
)
from app.runtime.recovery_event_service import (
    RecoveryEventService,
)
from app.runtime.recovery_models import (
    RecoveryAttempt,
    RecoveryResult,
    RecoveryStatus,
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
    source: RecoverySource = RecoverySource.RUNTIME,
    category: RecoveryEventCategory = (
        RecoveryEventCategory.RECOVERY
    ),
    status: RecoveryEventStatus = (
        RecoveryEventStatus.SUCCEEDED
    ),
    started_at: datetime = BASE_TIME,
    completed_at: datetime | None = (
        BASE_TIME + timedelta(seconds=1)
    ),
    message: str | None = None,
) -> RecoveryEvent:
    """テスト用RecoveryEventを生成する。"""

    if status in {
        RecoveryEventStatus.FAILED,
        RecoveryEventStatus.ABORTED,
    } and message is None:
        message = "recovery failed"

    return RecoveryEvent(
        event_id=event_id,
        source=source,
        category=category,
        status=status,
        name=f"{source.value} recovery",
        started_at=started_at,
        completed_at=completed_at,
        message=message,
    )


def make_runtime_result(
    *,
    recovery_name: str = "runtime restart",
    status: RecoveryStatus = RecoveryStatus.SUCCESS,
    successful: bool = True,
    message: str | None = None,
) -> RecoveryResult:
    """テスト用Runtime RecoveryResultを生成する。"""

    attempts: tuple[RecoveryAttempt, ...]

    if status is RecoveryStatus.ABORTED:
        attempts = ()
    else:
        attempts = (
            RecoveryAttempt(
                attempt_number=1,
                started_at=BASE_TIME,
                completed_at=(
                    BASE_TIME
                    + timedelta(seconds=1)
                ),
                successful=successful,
                error_message=(
                    None
                    if successful
                    else "runtime failed"
                ),
                delay_seconds_before_attempt=0.0,
            ),
        )

    return RecoveryResult(
        recovery_name=recovery_name,
        status=status,
        started_at=BASE_TIME,
        completed_at=(
            BASE_TIME + timedelta(seconds=1)
        ),
        attempts=attempts,
        message=message,
    )


def test_record_saves_existing_event() -> None:
    """生成済みRecoveryEventを保存できる。"""

    repository = RecoveryEventRepository()
    service = RecoveryEventService(repository)
    event = make_event(event_id="event-1")

    saved = service.record(event)

    assert saved is event
    assert service.list_events() == (event,)
    assert service.count() == 1


def test_record_runtime_result_maps_and_saves_event() -> None:
    """Runtime結果をEventへ変換して保存できる。"""

    repository = RecoveryEventRepository()
    service = RecoveryEventService(repository)
    result = make_runtime_result()

    event = service.record_runtime_result(result)

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
    assert event.metadata["attempt_count"] == 1
    assert service.list_events() == (event,)


def test_record_runtime_result_accepts_category() -> None:
    """Runtime結果に明示した分類を設定できる。"""

    service = RecoveryEventService(
        RecoveryEventRepository()
    )

    event = service.record_runtime_result(
        make_runtime_result(),
        category=RecoveryEventCategory.RESTART,
    )

    assert (
        event.category
        is RecoveryEventCategory.RESTART
    )


def test_record_runtime_failed_result() -> None:
    """失敗したRuntime結果を保存できる。"""

    service = RecoveryEventService(
        RecoveryEventRepository()
    )
    result = make_runtime_result(
        status=RecoveryStatus.FAILED,
        successful=False,
    )

    event = service.record_runtime_result(result)

    assert (
        event.status
        is RecoveryEventStatus.FAILED
    )
    assert event.message == "runtime failed"
    assert event.failed is True


def test_record_runtime_retrying_result() -> None:
    """再試行中Runtime結果を進行中Eventとして保存できる。"""

    service = RecoveryEventService(
        RecoveryEventRepository()
    )
    result = make_runtime_result(
        status=RecoveryStatus.RETRYING,
        successful=False,
        message="retrying",
    )

    event = service.record_runtime_result(result)

    assert (
        event.status
        is RecoveryEventStatus.RETRYING
    )
    assert event.completed_at is None
    assert event.is_terminal is False
    assert event.message == "retrying"


def test_list_events_filters_multiple_conditions() -> None:
    """複数条件でRecoveryEventを絞り込める。"""

    repository = RecoveryEventRepository()
    service = RecoveryEventService(repository)

    runtime_failed = make_event(
        event_id="runtime-failed",
        source=RecoverySource.RUNTIME,
        category=RecoveryEventCategory.RESTART,
        status=RecoveryEventStatus.FAILED,
    )
    runtime_success = make_event(
        event_id="runtime-success",
        source=RecoverySource.RUNTIME,
        category=RecoveryEventCategory.RESTART,
        started_at=BASE_TIME + timedelta(minutes=1),
        completed_at=BASE_TIME + timedelta(
            minutes=1,
            seconds=1,
        ),
    )
    broker_success = make_event(
        event_id="broker-success",
        source=RecoverySource.BROKER,
        category=RecoveryEventCategory.RECONNECT,
        started_at=BASE_TIME + timedelta(minutes=2),
        completed_at=BASE_TIME + timedelta(
            minutes=2,
            seconds=1,
        ),
    )

    service.record(runtime_failed)
    service.record(runtime_success)
    service.record(broker_success)

    assert service.list_events(
        source=RecoverySource.RUNTIME,
        category=RecoveryEventCategory.RESTART,
        status=RecoveryEventStatus.FAILED,
    ) == (runtime_failed,)


def test_latest_returns_latest_event() -> None:
    """最新RecoveryEventを取得できる。"""

    service = RecoveryEventService(
        RecoveryEventRepository()
    )
    earlier = make_event(event_id="earlier")
    later = make_event(
        event_id="later",
        started_at=BASE_TIME + timedelta(minutes=1),
        completed_at=BASE_TIME + timedelta(
            minutes=1,
            seconds=1,
        ),
    )

    service.record(later)
    service.record(earlier)

    assert service.latest() is later


def test_latest_filters_by_source() -> None:
    """発生元別に最新RecoveryEventを取得できる。"""

    service = RecoveryEventService(
        RecoveryEventRepository()
    )
    runtime_event = make_event(
        event_id="runtime",
        source=RecoverySource.RUNTIME,
    )
    broker_event = make_event(
        event_id="broker",
        source=RecoverySource.BROKER,
        started_at=BASE_TIME + timedelta(minutes=1),
        completed_at=BASE_TIME + timedelta(
            minutes=1,
            seconds=1,
        ),
    )

    service.record(runtime_event)
    service.record(broker_event)

    assert service.latest(
        source=RecoverySource.RUNTIME
    ) is runtime_event
    assert service.latest(
        source=RecoverySource.BROKER
    ) is broker_event
    assert service.latest(
        source=RecoverySource.LIVE
    ) is None


def test_count_delegates_filters_to_repository() -> None:
    """条件付きEvent件数を取得できる。"""

    service = RecoveryEventService(
        RecoveryEventRepository()
    )

    service.record(
        make_event(
            event_id="runtime-failed",
            source=RecoverySource.RUNTIME,
            status=RecoveryEventStatus.FAILED,
        )
    )
    service.record(
        make_event(
            event_id="runtime-success",
            source=RecoverySource.RUNTIME,
            started_at=BASE_TIME + timedelta(minutes=1),
            completed_at=BASE_TIME + timedelta(
                minutes=1,
                seconds=1,
            ),
        )
    )

    assert service.count() == 2
    assert service.count(
        source=RecoverySource.RUNTIME,
        status=RecoveryEventStatus.FAILED,
    ) == 1


def test_clear_removes_all_events() -> None:
    """保存済みRecoveryEventを削除できる。"""

    service = RecoveryEventService(
        RecoveryEventRepository()
    )
    service.record(
        make_event(event_id="event-1")
    )

    service.clear()

    assert service.list_events() == ()
    assert service.latest() is None
    assert service.count() == 0


def test_service_accepts_sqlite_repository(
    tmp_path,
) -> None:
    """SQLite RepositoryもServiceから利用できる。"""

    database_path = tmp_path / "katana.db"
    service = RecoveryEventService(
        SQLiteRecoveryEventRepository(
            database_path
        )
    )

    event = service.record_runtime_result(
        make_runtime_result()
    )

    reloaded_service = RecoveryEventService(
        SQLiteRecoveryEventRepository(
            database_path
        )
    )

    assert reloaded_service.latest() == event
    assert reloaded_service.count() == 1


def test_service_rejects_invalid_repository() -> None:
    """RecoveryEventRepository以外を拒否する。"""

    with pytest.raises(
        TypeError,
        match=(
            "repository must be a "
            "RecoveryEventRepository"
        ),
    ):
        RecoveryEventService(
            repository="invalid"
        )


def test_record_rejects_invalid_event() -> None:
    """RecoveryEvent以外を拒否する。"""

    service = RecoveryEventService(
        RecoveryEventRepository()
    )

    with pytest.raises(
        TypeError,
        match="event must be a RecoveryEvent",
    ):
        service.record("invalid")


def test_record_runtime_result_rejects_invalid_result() -> None:
    """Runtime RecoveryResult以外を拒否する。"""

    service = RecoveryEventService(
        RecoveryEventRepository()
    )

    with pytest.raises(
        TypeError,
        match="result must be a RecoveryResult",
    ):
        service.record_runtime_result("invalid")


def test_record_runtime_result_rejects_invalid_category() -> None:
    """RecoveryEventCategory以外を拒否する。"""

    service = RecoveryEventService(
        RecoveryEventRepository()
    )

    with pytest.raises(
        TypeError,
        match=(
            "category must be a RecoveryEventCategory"
        ),
    ):
        service.record_runtime_result(
            make_runtime_result(),
            category="restart",
        )


@pytest.mark.parametrize(
    (
        "method_name",
        "keyword",
        "value",
        "message",
    ),
    [
        (
            "list_events",
            "source",
            "runtime",
            "source must be a RecoverySource or None",
        ),
        (
            "list_events",
            "category",
            "restart",
            (
                "category must be a "
                "RecoveryEventCategory or None"
            ),
        ),
        (
            "list_events",
            "status",
            "failed",
            (
                "status must be a "
                "RecoveryEventStatus or None"
            ),
        ),
        (
            "count",
            "source",
            "runtime",
            "source must be a RecoverySource or None",
        ),
    ],
)
def test_filter_methods_reject_invalid_types(
    method_name: str,
    keyword: str,
    value: object,
    message: str,
) -> None:
    """検索条件に不正な型を指定できない。"""

    service = RecoveryEventService(
        RecoveryEventRepository()
    )
    method = getattr(service, method_name)

    with pytest.raises(
        TypeError,
        match=message,
    ):
        method(**{keyword: value})


def test_latest_rejects_invalid_source() -> None:
    """latestはRecoverySource以外を拒否する。"""

    service = RecoveryEventService(
        RecoveryEventRepository()
    )

    with pytest.raises(
        TypeError,
        match="source must be a RecoverySource or None",
    ):
        service.latest(source="runtime")