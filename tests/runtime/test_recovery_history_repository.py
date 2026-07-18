"""RecoveryHistoryRepositoryのユニットテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.runtime.recovery_history_models import (
    RecoveryComponent,
    RecoveryHistoryEntry,
)
from app.runtime.recovery_history_repository import (
    RecoveryHistoryRepository,
)
from app.runtime.recovery_models import (
    RecoveryAttempt,
    RecoveryResult,
    RecoveryStatus,
)


def make_result(
    *,
    recovery_name: str,
    completed_at: datetime,
    successful: bool = True,
) -> RecoveryResult:
    """テスト用RecoveryResultを生成する。"""

    started_at = completed_at - timedelta(seconds=1)

    attempt = RecoveryAttempt(
        attempt_number=1,
        started_at=started_at,
        completed_at=completed_at,
        successful=successful,
        error_message=None if successful else "recovery failed",
        delay_seconds_before_attempt=0.0,
    )

    return RecoveryResult(
        recovery_name=recovery_name,
        status=(
            RecoveryStatus.SUCCESS
            if successful
            else RecoveryStatus.FAILED
        ),
        started_at=started_at,
        completed_at=completed_at,
        attempts=(attempt,),
    )


def test_repository_is_empty_initially() -> None:
    """初期状態では履歴が存在しない。"""

    repository = RecoveryHistoryRepository()

    assert repository.list_all() == ()
    assert repository.latest() is None
    assert repository.count() == 0


def test_add_and_list_all() -> None:
    """追加した履歴を取得できる。"""

    repository = RecoveryHistoryRepository()
    completed_at = datetime(
        2026,
        7,
        18,
        1,
        0,
        tzinfo=timezone.utc,
    )

    entry = RecoveryHistoryEntry(
        component=RecoveryComponent.BROKER,
        result=make_result(
            recovery_name="broker_reconnect",
            completed_at=completed_at,
        ),
    )

    repository.add(entry)

    assert repository.list_all() == (entry,)
    assert repository.count() == 1


def test_entries_are_sorted_by_completed_at() -> None:
    """履歴は追加順ではなく完了日時順になる。"""

    repository = RecoveryHistoryRepository()
    base_time = datetime(
        2026,
        7,
        18,
        1,
        0,
        tzinfo=timezone.utc,
    )

    later_entry = RecoveryHistoryEntry(
        component=RecoveryComponent.RUNTIME,
        result=make_result(
            recovery_name="runtime_restart",
            completed_at=base_time + timedelta(minutes=10),
        ),
    )
    earlier_entry = RecoveryHistoryEntry(
        component=RecoveryComponent.BROKER,
        result=make_result(
            recovery_name="broker_reconnect",
            completed_at=base_time,
        ),
    )

    repository.add(later_entry)
    repository.add(earlier_entry)

    assert repository.list_all() == (
        earlier_entry,
        later_entry,
    )
    assert repository.latest() == later_entry


def test_list_by_component() -> None:
    """コンポーネント別に履歴を取得できる。"""

    repository = RecoveryHistoryRepository()
    base_time = datetime(
        2026,
        7,
        18,
        1,
        0,
        tzinfo=timezone.utc,
    )

    broker_entry = RecoveryHistoryEntry(
        component=RecoveryComponent.BROKER,
        result=make_result(
            recovery_name="broker_reconnect",
            completed_at=base_time,
        ),
    )
    runtime_entry = RecoveryHistoryEntry(
        component=RecoveryComponent.RUNTIME,
        result=make_result(
            recovery_name="runtime_restart",
            completed_at=base_time + timedelta(minutes=1),
        ),
    )

    repository.add(broker_entry)
    repository.add(runtime_entry)

    assert repository.list_by_component(
        RecoveryComponent.BROKER
    ) == (broker_entry,)
    assert repository.list_by_component(
        RecoveryComponent.RUNTIME
    ) == (runtime_entry,)


def test_latest_by_component() -> None:
    """コンポーネント別の最新履歴を取得できる。"""

    repository = RecoveryHistoryRepository()
    base_time = datetime(
        2026,
        7,
        18,
        1,
        0,
        tzinfo=timezone.utc,
    )

    first_entry = RecoveryHistoryEntry(
        component=RecoveryComponent.BROKER,
        result=make_result(
            recovery_name="first",
            completed_at=base_time,
        ),
    )
    second_entry = RecoveryHistoryEntry(
        component=RecoveryComponent.BROKER,
        result=make_result(
            recovery_name="second",
            completed_at=base_time + timedelta(minutes=1),
        ),
    )

    repository.add(first_entry)
    repository.add(second_entry)

    assert repository.latest(
        RecoveryComponent.BROKER
    ) == second_entry
    assert repository.latest(
        RecoveryComponent.RUNTIME
    ) is None


def test_clear_removes_all_entries() -> None:
    """clearで全履歴を削除できる。"""

    repository = RecoveryHistoryRepository()
    completed_at = datetime(
        2026,
        7,
        18,
        1,
        0,
        tzinfo=timezone.utc,
    )

    repository.add(
        RecoveryHistoryEntry(
            component=RecoveryComponent.BROKER,
            result=make_result(
                recovery_name="broker_reconnect",
                completed_at=completed_at,
            ),
        )
    )

    repository.clear()

    assert repository.list_all() == ()
    assert repository.count() == 0


def test_add_rejects_invalid_type() -> None:
    """RecoveryHistoryEntry以外を拒否する。"""

    repository = RecoveryHistoryRepository()

    with pytest.raises(
        TypeError,
        match="entry must be a RecoveryHistoryEntry",
    ):
        repository.add("invalid")  # type: ignore[arg-type]