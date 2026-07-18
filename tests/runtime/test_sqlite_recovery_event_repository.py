"""SQLiteRecoveryEventRepositoryのユニットテスト。"""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.database import SCHEMA_VERSION, initialize_database
from app.runtime.recovery_event_models import (
    RecoveryEvent,
    RecoveryEventCategory,
    RecoveryEventStatus,
    RecoverySource,
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
    metadata: dict[str, object] | None = None,
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
        metadata={} if metadata is None else metadata,
    )


def test_initialize_database_creates_recovery_event_table(
    tmp_path,
) -> None:
    """共通DB初期化がEventテーブルとVersion 12を作成する。"""

    database_path = tmp_path / "katana.db"

    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }
        indexes = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'index'
                """
            ).fetchall()
        }
        version_row = connection.execute(
            """
            SELECT version
            FROM schema_version
            WHERE id = 1
            """
        ).fetchone()

    assert "recovery_events" in tables
    assert {
        "idx_recovery_events_event_id",
        "idx_recovery_events_started_at",
        "idx_recovery_events_source_started_at",
        "idx_recovery_events_status_started_at",
    } <= indexes
    assert version_row == (SCHEMA_VERSION,)
    assert SCHEMA_VERSION == 12


def test_repository_is_empty_initially(tmp_path) -> None:
    """初期状態ではEventが存在しない。"""

    repository = SQLiteRecoveryEventRepository(
        tmp_path / "katana.db"
    )

    assert repository.list_all() == ()
    assert repository.latest() is None
    assert repository.count() == 0


def test_add_and_reload_from_new_repository(tmp_path) -> None:
    """別Repositoryインスタンスから保存Eventを取得できる。"""

    database_path = tmp_path / "katana.db"
    writer = SQLiteRecoveryEventRepository(database_path)
    event = make_event(
        event_id="event-1",
        metadata={
            "attempt_count": 2,
            "attempts": (
                {"successful": False},
                {"successful": True},
            ),
        },
    )

    saved = writer.add(event)
    reader = SQLiteRecoveryEventRepository(database_path)

    assert saved is event
    assert reader.list_all() == (event,)
    assert reader.get_by_id("event-1") == event
    assert reader.count() == 1


def test_list_all_is_sorted_chronologically(tmp_path) -> None:
    """Eventを開始日時順で返す。"""

    repository = SQLiteRecoveryEventRepository(
        tmp_path / "katana.db"
    )
    later = make_event(
        event_id="later",
        started_at=BASE_TIME + timedelta(minutes=10),
        completed_at=BASE_TIME + timedelta(
            minutes=10,
            seconds=1,
        ),
    )
    earlier = make_event(event_id="earlier")

    repository.add(later)
    repository.add(earlier)

    assert repository.list_all() == (earlier, later)
    assert repository.latest() == later


def test_active_event_is_persisted(tmp_path) -> None:
    """completed_atのない進行中Eventを保存できる。"""

    repository = SQLiteRecoveryEventRepository(
        tmp_path / "katana.db"
    )
    event = make_event(
        event_id="retrying",
        status=RecoveryEventStatus.RETRYING,
        completed_at=None,
        message="retrying",
    )

    repository.add(event)

    assert repository.latest() == event


def test_filter_methods_and_count(tmp_path) -> None:
    """発生元・分類・状態でEventを検索できる。"""

    repository = SQLiteRecoveryEventRepository(
        tmp_path / "katana.db"
    )
    runtime_failed = make_event(
        event_id="runtime-failed",
        source=RecoverySource.RUNTIME,
        category=RecoveryEventCategory.RESTART,
        status=RecoveryEventStatus.FAILED,
    )
    broker_success = make_event(
        event_id="broker-success",
        source=RecoverySource.BROKER,
        category=RecoveryEventCategory.RECONNECT,
        started_at=BASE_TIME + timedelta(minutes=1),
        completed_at=BASE_TIME + timedelta(
            minutes=1,
            seconds=1,
        ),
    )

    repository.add(runtime_failed)
    repository.add(broker_success)

    assert repository.list_by_source(
        RecoverySource.RUNTIME
    ) == (runtime_failed,)
    assert repository.list_by_category(
        RecoveryEventCategory.RECONNECT
    ) == (broker_success,)
    assert repository.list_by_status(
        RecoveryEventStatus.FAILED
    ) == (runtime_failed,)
    assert repository.latest(
        source=RecoverySource.BROKER
    ) == broker_success
    assert repository.latest(
        source=RecoverySource.LIVE
    ) is None
    assert repository.count() == 2
    assert repository.count(
        source=RecoverySource.RUNTIME,
        category=RecoveryEventCategory.RESTART,
        status=RecoveryEventStatus.FAILED,
    ) == 1


def test_duplicate_event_id_raises_value_error(tmp_path) -> None:
    """同一Event IDの重複保存を統一例外で拒否する。"""

    repository = SQLiteRecoveryEventRepository(
        tmp_path / "katana.db"
    )
    repository.add(make_event(event_id="duplicate"))

    with pytest.raises(
        ValueError,
        match=(
            "RecoveryEvent with the same event_id "
            "already exists"
        ),
    ):
        repository.add(
            make_event(
                event_id="duplicate",
                source=RecoverySource.BROKER,
            )
        )


def test_clear_removes_all_events(tmp_path) -> None:
    """clearですべてのEventを削除する。"""

    repository = SQLiteRecoveryEventRepository(
        tmp_path / "katana.db"
    )
    repository.add(make_event(event_id="event-1"))
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


def test_add_rejects_invalid_event_type(tmp_path) -> None:
    """RecoveryEvent以外を拒否する。"""

    repository = SQLiteRecoveryEventRepository(
        tmp_path / "katana.db"
    )

    with pytest.raises(
        TypeError,
        match="event must be a RecoveryEvent",
    ):
        repository.add("invalid")


def test_filter_methods_reject_invalid_types(tmp_path) -> None:
    """検索条件Enum以外を拒否する。"""

    repository = SQLiteRecoveryEventRepository(
        tmp_path / "katana.db"
    )

    with pytest.raises(
        TypeError,
        match="source must be a RecoverySource",
    ):
        repository.list_by_source("runtime")

    with pytest.raises(
        TypeError,
        match="category must be a RecoveryEventCategory",
    ):
        repository.list_by_category("restart")

    with pytest.raises(
        TypeError,
        match="status must be a RecoveryEventStatus",
    ):
        repository.list_by_status("failed")


def test_unsupported_metadata_value_is_rejected(tmp_path) -> None:
    """SQLiteへ保存できないMetadata値を拒否する。"""

    repository = SQLiteRecoveryEventRepository(
        tmp_path / "katana.db"
    )
    event = make_event(
        event_id="invalid-metadata",
        metadata={"value": object()},
    )

    with pytest.raises(
        TypeError,
        match=(
            "metadata must contain JSON-compatible values"
        ),
    ):
        repository.add(event)
