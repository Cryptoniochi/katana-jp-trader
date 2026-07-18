"""SQLiteRecoveryHistoryRepositoryのユニットテスト。"""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.database import (
    SCHEMA_VERSION,
    initialize_database,
)
from app.runtime.recovery_history_models import (
    RecoveryComponent,
    RecoveryHistoryEntry,
)
from app.runtime.recovery_models import (
    RecoveryAttempt,
    RecoveryResult,
    RecoveryStatus,
)
from app.runtime.sqlite_recovery_history_repository import (
    SQLiteRecoveryHistoryRepository,
)


BASE_TIME = datetime(
    2026,
    7,
    18,
    1,
    0,
    tzinfo=timezone.utc,
)


def make_result(
    *,
    recovery_name: str,
    started_at: datetime,
    attempt_successes: tuple[bool, ...],
    status: RecoveryStatus,
    message: str | None = None,
) -> RecoveryResult:
    """テスト用RecoveryResultを作成する。"""

    attempts = tuple(
        RecoveryAttempt(
            attempt_number=index,
            started_at=(
                started_at
                + timedelta(seconds=index - 1)
            ),
            completed_at=(
                started_at
                + timedelta(seconds=index)
            ),
            successful=successful,
            error_message=(
                None
                if successful
                else f"failed-{index}"
            ),
            delay_seconds_before_attempt=float(
                index - 1
            ),
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
        message=message,
    )


def test_initialize_database_creates_recovery_tables(
    tmp_path,
) -> None:
    """共通DB初期化がRecoveryテーブルとVersion 12を作成する。"""

    database_path = tmp_path / "katana.db"

    initialize_database(database_path)

    with sqlite3.connect(
        database_path
    ) as connection:
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
        version_row = connection.execute(
            """
            SELECT version
            FROM schema_version
            WHERE id = 1
            """
        ).fetchone()

    assert "recovery_history" in tables
    assert "recovery_attempts" in tables
    assert version_row == (SCHEMA_VERSION,)
    assert SCHEMA_VERSION == 12


def test_repository_is_empty_initially(
    tmp_path,
) -> None:
    """初期状態では履歴が存在しない。"""

    repository = SQLiteRecoveryHistoryRepository(
        tmp_path / "katana.db"
    )

    assert repository.list_all() == ()
    assert repository.latest() is None
    assert repository.count() == 0


def test_add_and_reload_from_new_repository(
    tmp_path,
) -> None:
    """別Repositoryインスタンスから保存結果を取得できる。"""

    database_path = tmp_path / "katana.db"
    writer = SQLiteRecoveryHistoryRepository(
        database_path
    )

    result = make_result(
        recovery_name="broker_reconnect",
        started_at=BASE_TIME,
        attempt_successes=(False, True),
        status=RecoveryStatus.SUCCESS,
    )
    entry = RecoveryHistoryEntry(
        component=RecoveryComponent.BROKER,
        result=result,
    )

    writer.add(entry)

    reader = SQLiteRecoveryHistoryRepository(
        database_path
    )
    loaded = reader.list_all()

    assert loaded == (entry,)
    assert reader.count() == 1


def test_list_all_is_sorted_by_completed_at(
    tmp_path,
) -> None:
    """履歴を完了日時の昇順で返す。"""

    repository = SQLiteRecoveryHistoryRepository(
        tmp_path / "katana.db"
    )

    later = RecoveryHistoryEntry(
        component=RecoveryComponent.RUNTIME,
        result=make_result(
            recovery_name="runtime_restart",
            started_at=BASE_TIME
            + timedelta(minutes=10),
            attempt_successes=(True,),
            status=RecoveryStatus.SUCCESS,
        ),
    )
    earlier = RecoveryHistoryEntry(
        component=RecoveryComponent.BROKER,
        result=make_result(
            recovery_name="broker_reconnect",
            started_at=BASE_TIME,
            attempt_successes=(True,),
            status=RecoveryStatus.SUCCESS,
        ),
    )

    repository.add(later)
    repository.add(earlier)

    assert repository.list_all() == (
        earlier,
        later,
    )
    assert repository.latest() == later


def test_list_and_count_by_component(
    tmp_path,
) -> None:
    """コンポーネント別の履歴と件数を取得できる。"""

    repository = SQLiteRecoveryHistoryRepository(
        tmp_path / "katana.db"
    )

    broker = RecoveryHistoryEntry(
        component=RecoveryComponent.BROKER,
        result=make_result(
            recovery_name="broker_reconnect",
            started_at=BASE_TIME,
            attempt_successes=(True,),
            status=RecoveryStatus.SUCCESS,
        ),
    )
    runtime = RecoveryHistoryEntry(
        component=RecoveryComponent.RUNTIME,
        result=make_result(
            recovery_name="runtime_restart",
            started_at=BASE_TIME
            + timedelta(minutes=1),
            attempt_successes=(False,),
            status=RecoveryStatus.FAILED,
        ),
    )

    repository.add(broker)
    repository.add(runtime)

    assert repository.list_by_component(
        RecoveryComponent.BROKER
    ) == (broker,)
    assert repository.list_by_component(
        RecoveryComponent.RUNTIME
    ) == (runtime,)

    assert repository.count(
        RecoveryComponent.BROKER
    ) == 1
    assert repository.count(
        RecoveryComponent.RUNTIME
    ) == 1


def test_retrying_result_without_attempts_is_persisted(
    tmp_path,
) -> None:
    """試行前のRETRYING状態も保存・復元できる。"""

    repository = SQLiteRecoveryHistoryRepository(
        tmp_path / "katana.db"
    )

    entry = RecoveryHistoryEntry(
        component=RecoveryComponent.RUNTIME,
        result=make_result(
            recovery_name="runtime_retry",
            started_at=BASE_TIME,
            attempt_successes=(),
            status=RecoveryStatus.RETRYING,
        ),
    )

    repository.add(entry)

    assert repository.latest() == entry


def test_aborted_result_message_is_persisted(
    tmp_path,
) -> None:
    """ABORTED理由を保存・復元できる。"""

    repository = SQLiteRecoveryHistoryRepository(
        tmp_path / "katana.db"
    )

    entry = RecoveryHistoryEntry(
        component=RecoveryComponent.RUNTIME,
        result=make_result(
            recovery_name="runtime_abort",
            started_at=BASE_TIME,
            attempt_successes=(),
            status=RecoveryStatus.ABORTED,
            message="manual shutdown",
        ),
    )

    repository.add(entry)

    loaded = repository.latest()

    assert loaded == entry
    assert loaded is not None
    assert loaded.result.message == "manual shutdown"


def test_clear_removes_history_and_attempts(
    tmp_path,
) -> None:
    """clearで親履歴と試行履歴を削除する。"""

    database_path = tmp_path / "katana.db"
    repository = SQLiteRecoveryHistoryRepository(
        database_path
    )

    repository.add(
        RecoveryHistoryEntry(
            component=RecoveryComponent.BROKER,
            result=make_result(
                recovery_name="broker_reconnect",
                started_at=BASE_TIME,
                attempt_successes=(False, True),
                status=RecoveryStatus.SUCCESS,
            ),
        )
    )

    repository.clear()

    assert repository.count() == 0
    assert repository.list_all() == ()

    with sqlite3.connect(
        database_path
    ) as connection:
        attempt_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM recovery_attempts
            """
        ).fetchone()

    assert attempt_count == (0,)


def test_add_rejects_invalid_type(
    tmp_path,
) -> None:
    """RecoveryHistoryEntry以外を拒否する。"""

    repository = SQLiteRecoveryHistoryRepository(
        tmp_path / "katana.db"
    )

    with pytest.raises(
        TypeError,
        match="entry must be a RecoveryHistoryEntry",
    ):
        repository.add("invalid")  # type: ignore[arg-type]


def test_component_methods_reject_invalid_type(
    tmp_path,
) -> None:
    """RecoveryComponent以外を拒否する。"""

    repository = SQLiteRecoveryHistoryRepository(
        tmp_path / "katana.db"
    )

    with pytest.raises(
        TypeError,
        match="component must be a RecoveryComponent",
    ):
        repository.list_by_component(  # type: ignore[arg-type]
            "broker"
        )

    with pytest.raises(
        TypeError,
        match="component must be a RecoveryComponent",
    ):
        repository.latest(  # type: ignore[arg-type]
            "broker"
        )

    with pytest.raises(
        TypeError,
        match="component must be a RecoveryComponent",
    ):
        repository.count(  # type: ignore[arg-type]
            "broker"
        )
