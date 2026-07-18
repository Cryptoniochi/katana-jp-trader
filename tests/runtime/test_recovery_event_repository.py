"""RecoveryEventRepositoryのユニットテスト。"""

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


def test_add_saves_event() -> None:
    """RecoveryEventを保存できる。"""

    repository = RecoveryEventRepository()
    event = make_event(event_id="event-1")

    saved = repository.add(event)

    assert saved is event
    assert repository.list_all() == (event,)
    assert repository.count() == 1


def test_events_are_returned_in_chronological_order() -> None:
    """追加順に関係なく時系列順で返す。"""

    repository = RecoveryEventRepository()

    later_event = make_event(
        event_id="event-later",
        started_at=BASE_TIME + timedelta(minutes=10),
        completed_at=BASE_TIME + timedelta(
            minutes=10,
            seconds=1,
        ),
    )
    earlier_event = make_event(
        event_id="event-earlier",
        started_at=BASE_TIME,
        completed_at=BASE_TIME + timedelta(seconds=1),
    )

    repository.add(later_event)
    repository.add(earlier_event)

    assert repository.list_all() == (
        earlier_event,
        later_event,
    )


def test_add_rejects_duplicate_event_id() -> None:
    """同一Event IDの重複保存を拒否する。"""

    repository = RecoveryEventRepository()

    repository.add(
        make_event(event_id="duplicate-event")
    )

    with pytest.raises(
        ValueError,
        match=(
            "RecoveryEvent with the same event_id "
            "already exists"
        ),
    ):
        repository.add(
            make_event(
                event_id="duplicate-event",
                source=RecoverySource.BROKER,
            )
        )


def test_get_by_id_returns_matching_event() -> None:
    """Event IDでRecoveryEventを取得できる。"""

    repository = RecoveryEventRepository()
    first_event = make_event(event_id="event-1")
    second_event = make_event(
        event_id="event-2",
        source=RecoverySource.BROKER,
    )

    repository.add(first_event)
    repository.add(second_event)

    assert repository.get_by_id("event-2") is second_event
    assert repository.get_by_id("missing") is None


def test_list_by_source_filters_events() -> None:
    """発生元ごとにRecoveryEventを取得できる。"""

    repository = RecoveryEventRepository()
    runtime_event = make_event(
        event_id="runtime-event",
        source=RecoverySource.RUNTIME,
    )
    broker_event = make_event(
        event_id="broker-event",
        source=RecoverySource.BROKER,
        started_at=BASE_TIME + timedelta(minutes=1),
        completed_at=BASE_TIME + timedelta(
            minutes=1,
            seconds=1,
        ),
    )

    repository.add(runtime_event)
    repository.add(broker_event)

    assert repository.list_by_source(
        RecoverySource.RUNTIME
    ) == (runtime_event,)
    assert repository.list_by_source(
        RecoverySource.BROKER
    ) == (broker_event,)


def test_list_by_category_filters_events() -> None:
    """分類ごとにRecoveryEventを取得できる。"""

    repository = RecoveryEventRepository()
    restart_event = make_event(
        event_id="restart-event",
        category=RecoveryEventCategory.RESTART,
    )
    audit_event = make_event(
        event_id="audit-event",
        category=RecoveryEventCategory.AUDIT,
        started_at=BASE_TIME + timedelta(minutes=1),
        completed_at=BASE_TIME + timedelta(
            minutes=1,
            seconds=1,
        ),
    )

    repository.add(restart_event)
    repository.add(audit_event)

    assert repository.list_by_category(
        RecoveryEventCategory.RESTART
    ) == (restart_event,)
    assert repository.list_by_category(
        RecoveryEventCategory.AUDIT
    ) == (audit_event,)


def test_list_by_status_filters_events() -> None:
    """状態ごとにRecoveryEventを取得できる。"""

    repository = RecoveryEventRepository()
    success_event = make_event(
        event_id="success-event",
        status=RecoveryEventStatus.SUCCEEDED,
    )
    failed_event = make_event(
        event_id="failed-event",
        status=RecoveryEventStatus.FAILED,
        started_at=BASE_TIME + timedelta(minutes=1),
        completed_at=BASE_TIME + timedelta(
            minutes=1,
            seconds=1,
        ),
    )

    repository.add(success_event)
    repository.add(failed_event)

    assert repository.list_by_status(
        RecoveryEventStatus.SUCCEEDED
    ) == (success_event,)
    assert repository.list_by_status(
        RecoveryEventStatus.FAILED
    ) == (failed_event,)


def test_latest_returns_latest_event() -> None:
    """全体の最新RecoveryEventを返す。"""

    repository = RecoveryEventRepository()
    earlier_event = make_event(
        event_id="earlier-event",
    )
    later_event = make_event(
        event_id="later-event",
        started_at=BASE_TIME + timedelta(minutes=5),
        completed_at=BASE_TIME + timedelta(
            minutes=5,
            seconds=1,
        ),
    )

    repository.add(later_event)
    repository.add(earlier_event)

    assert repository.latest() is later_event


def test_latest_filters_by_source() -> None:
    """指定した発生元の最新RecoveryEventを返す。"""

    repository = RecoveryEventRepository()
    runtime_event = make_event(
        event_id="runtime-event",
        source=RecoverySource.RUNTIME,
    )
    broker_event = make_event(
        event_id="broker-event",
        source=RecoverySource.BROKER,
        started_at=BASE_TIME + timedelta(minutes=5),
        completed_at=BASE_TIME + timedelta(
            minutes=5,
            seconds=1,
        ),
    )

    repository.add(runtime_event)
    repository.add(broker_event)

    assert repository.latest(
        source=RecoverySource.RUNTIME
    ) is runtime_event
    assert repository.latest(
        source=RecoverySource.BROKER
    ) is broker_event
    assert repository.latest(
        source=RecoverySource.LIVE
    ) is None


def test_latest_returns_none_when_empty() -> None:
    """空Repositoryでは最新Eventが存在しない。"""

    repository = RecoveryEventRepository()

    assert repository.latest() is None


def test_count_filters_by_multiple_conditions() -> None:
    """複数条件を組み合わせて件数を取得できる。"""

    repository = RecoveryEventRepository()

    repository.add(
        make_event(
            event_id="runtime-success",
            source=RecoverySource.RUNTIME,
            category=RecoveryEventCategory.RESTART,
            status=RecoveryEventStatus.SUCCEEDED,
        )
    )
    repository.add(
        make_event(
            event_id="runtime-failed",
            source=RecoverySource.RUNTIME,
            category=RecoveryEventCategory.RESTART,
            status=RecoveryEventStatus.FAILED,
            started_at=BASE_TIME + timedelta(minutes=1),
            completed_at=BASE_TIME + timedelta(
                minutes=1,
                seconds=1,
            ),
        )
    )
    repository.add(
        make_event(
            event_id="broker-success",
            source=RecoverySource.BROKER,
            category=RecoveryEventCategory.RECONNECT,
            status=RecoveryEventStatus.SUCCEEDED,
            started_at=BASE_TIME + timedelta(minutes=2),
            completed_at=BASE_TIME + timedelta(
                minutes=2,
                seconds=1,
            ),
        )
    )

    assert repository.count() == 3
    assert repository.count(
        source=RecoverySource.RUNTIME
    ) == 2
    assert repository.count(
        source=RecoverySource.RUNTIME,
        category=RecoveryEventCategory.RESTART,
        status=RecoveryEventStatus.FAILED,
    ) == 1


def test_clear_removes_all_events() -> None:
    """保存済みRecoveryEventをすべて削除する。"""

    repository = RecoveryEventRepository()

    repository.add(
        make_event(event_id="event-1")
    )
    repository.add(
        make_event(
            event_id="event-2",
            started_at=BASE_TIME + timedelta(minutes=1),
            completed_at=BASE_TIME + timedelta(
                minutes=1,
                seconds=1,
            ),
        )
    )

    repository.clear()

    assert repository.list_all() == ()
    assert repository.latest() is None
    assert repository.count() == 0


def test_add_rejects_invalid_event_type() -> None:
    """RecoveryEvent以外を拒否する。"""

    repository = RecoveryEventRepository()

    with pytest.raises(
        TypeError,
        match="event must be a RecoveryEvent",
    ):
        repository.add("invalid")


def test_get_by_id_rejects_empty_event_id() -> None:
    """空のEvent IDを拒否する。"""

    repository = RecoveryEventRepository()

    with pytest.raises(
        ValueError,
        match="event_id must not be empty",
    ):
        repository.get_by_id("   ")


def test_list_by_source_rejects_invalid_type() -> None:
    """RecoverySource以外を拒否する。"""

    repository = RecoveryEventRepository()

    with pytest.raises(
        TypeError,
        match="source must be a RecoverySource",
    ):
        repository.list_by_source("runtime")


def test_list_by_category_rejects_invalid_type() -> None:
    """RecoveryEventCategory以外を拒否する。"""

    repository = RecoveryEventRepository()

    with pytest.raises(
        TypeError,
        match=(
            "category must be a RecoveryEventCategory"
        ),
    ):
        repository.list_by_category("restart")


def test_list_by_status_rejects_invalid_type() -> None:
    """RecoveryEventStatus以外を拒否する。"""

    repository = RecoveryEventRepository()

    with pytest.raises(
        TypeError,
        match=(
            "status must be a RecoveryEventStatus"
        ),
    ):
        repository.list_by_status("failed")