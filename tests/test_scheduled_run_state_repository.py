"""定刻実行状態Repositoryのテスト。"""

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.database import (
    SCHEMA_VERSION,
    initialize_database,
)
from app.trading.scheduled_run_state_repository import (
    ScheduledRunStateNotFoundError,
    ScheduledRunStateRepository,
)


TRADING_DATE = date(
    2026,
    7,
    20,
)

COMPLETED_AT = datetime(
    2026,
    7,
    20,
    0,
    30,
    tzinfo=timezone.utc,
)


def create_repository(
    tmp_path: Path,
) -> tuple[
    Path,
    ScheduledRunStateRepository,
]:
    """初期化済みDBとRepositoryを作成する。"""

    database_path = (
        tmp_path / "katana.db"
    )

    initialize_database(
        database_path,
    )

    return (
        database_path,
        ScheduledRunStateRepository(
            database_path,
        ),
    )


def test_initialize_database_creates_scheduled_run_states_table(
    tmp_path: Path,
) -> None:
    """DB初期化で定刻実行状態テーブルを作成する。"""

    database_path = (
        tmp_path / "katana.db"
    )

    initialize_database(
        database_path,
    )

    with sqlite3.connect(
        database_path,
    ) as connection:
        table_row = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'scheduled_run_states'
            """
        ).fetchone()

        version_row = connection.execute(
            """
            SELECT version
            FROM schema_version
            WHERE id = 1
            """
        ).fetchone()

    assert table_row == (
        "scheduled_run_states",
    )
    assert version_row == (
        SCHEMA_VERSION,
    )
def test_initialize_database_is_idempotent(
    tmp_path: Path,
) -> None:
    """DB初期化を複数回実行しても成功する。"""

    database_path = (
        tmp_path / "katana.db"
    )

    initialize_database(
        database_path,
    )
    initialize_database(
        database_path,
    )

    with sqlite3.connect(
        database_path,
    ) as connection:
        count_row = connection.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'scheduled_run_states'
            """
        ).fetchone()

    assert count_row == (
        1,
    )


def test_repository_marks_and_reads_completed_state(
    tmp_path: Path,
) -> None:
    """完了状態を保存して読み込む。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    repository.mark_completed(
        trading_date=TRADING_DATE,
        process_name="paper-trading",
        completed_at=COMPLETED_AT,
    )

    assert repository.has_completed(
        trading_date=TRADING_DATE,
        process_name="paper-trading",
    )

    record = repository.get(
        trading_date=TRADING_DATE,
        process_name="paper-trading",
    )

    assert record.id > 0
    assert record.trading_date == TRADING_DATE
    assert record.process_name == "paper-trading"
    assert record.completed_at == COMPLETED_AT
    assert record.created_at == COMPLETED_AT
    assert record.updated_at == COMPLETED_AT


def test_repository_preserves_first_completion_on_duplicate(
    tmp_path: Path,
) -> None:
    """同一日・同一処理の再登録では最初の完了を維持する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    later_time = (
        COMPLETED_AT
        + timedelta(
            minutes=10,
        )
    )

    repository.mark_completed(
        trading_date=TRADING_DATE,
        process_name="paper-trading",
        completed_at=COMPLETED_AT,
    )

    repository.mark_completed(
        trading_date=TRADING_DATE,
        process_name="paper-trading",
        completed_at=later_time,
    )

    record = repository.get(
        trading_date=TRADING_DATE,
        process_name="paper-trading",
    )

    assert repository.count() == 1
    assert record.completed_at == COMPLETED_AT


def test_repository_distinguishes_process_names(
    tmp_path: Path,
) -> None:
    """同じ日でも異なる処理名を別々に保存する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    repository.mark_completed(
        trading_date=TRADING_DATE,
        process_name="paper-trading",
        completed_at=COMPLETED_AT,
    )

    repository.mark_completed(
        trading_date=TRADING_DATE,
        process_name="jquants-update",
        completed_at=COMPLETED_AT,
    )

    assert repository.count() == 2

    assert repository.has_completed(
        trading_date=TRADING_DATE,
        process_name="paper-trading",
    )
    assert repository.has_completed(
        trading_date=TRADING_DATE,
        process_name="jquants-update",
    )


def test_repository_distinguishes_trading_dates(
    tmp_path: Path,
) -> None:
    """異なる取引日を別々に保存する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    next_date = (
        TRADING_DATE
        + timedelta(
            days=1,
        )
    )

    repository.mark_completed(
        trading_date=TRADING_DATE,
        process_name="paper-trading",
        completed_at=COMPLETED_AT,
    )

    repository.mark_completed(
        trading_date=next_date,
        process_name="paper-trading",
        completed_at=(
            COMPLETED_AT
            + timedelta(
                days=1,
            )
        ),
    )

    assert repository.count(
        process_name="paper-trading",
    ) == 2


def test_repository_returns_false_without_completion(
    tmp_path: Path,
) -> None:
    """保存されていない日付にはFalseを返す。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    assert not repository.has_completed(
        trading_date=TRADING_DATE,
        process_name="paper-trading",
    )
    assert repository.latest() is None


def test_repository_returns_latest_state(
    tmp_path: Path,
) -> None:
    """最新取引日の完了状態を返す。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    older_date = (
        TRADING_DATE
        - timedelta(
            days=1,
        )
    )

    repository.mark_completed(
        trading_date=older_date,
        process_name="paper-trading",
        completed_at=(
            COMPLETED_AT
            - timedelta(
                days=1,
            )
        ),
    )

    repository.mark_completed(
        trading_date=TRADING_DATE,
        process_name="paper-trading",
        completed_at=COMPLETED_AT,
    )

    latest = repository.latest(
        process_name="paper-trading",
    )

    assert latest is not None
    assert latest.trading_date == TRADING_DATE


def test_repository_lists_recent_states(
    tmp_path: Path,
) -> None:
    """完了状態を取引日の新しい順に返す。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    for offset in range(
        3,
    ):
        trading_date = (
            TRADING_DATE
            + timedelta(
                days=offset,
            )
        )

        repository.mark_completed(
            trading_date=trading_date,
            process_name="paper-trading",
            completed_at=(
                COMPLETED_AT
                + timedelta(
                    days=offset,
                )
            ),
        )

    records = repository.list_recent(
        limit=2,
    )

    assert [
        record.trading_date
        for record in records
    ] == [
        TRADING_DATE
        + timedelta(
            days=2,
        ),
        TRADING_DATE
        + timedelta(
            days=1,
        ),
    ]


def test_repository_filters_by_process_name(
    tmp_path: Path,
) -> None:
    """処理名で完了状態を絞り込む。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    repository.mark_completed(
        trading_date=TRADING_DATE,
        process_name="paper-trading",
        completed_at=COMPLETED_AT,
    )

    repository.mark_completed(
        trading_date=TRADING_DATE,
        process_name="jquants-update",
        completed_at=COMPLETED_AT,
    )

    records = repository.list_recent(
        process_name="jquants-update",
    )

    assert len(
        records,
    ) == 1
    assert records[0].process_name == (
        "jquants-update"
    )

    assert repository.count(
        process_name="paper-trading",
    ) == 1


def test_repository_rejects_missing_state(
    tmp_path: Path,
) -> None:
    """存在しない完了状態の取得を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    with pytest.raises(
        ScheduledRunStateNotFoundError,
        match="存在しません",
    ):
        repository.get(
            trading_date=TRADING_DATE,
            process_name="paper-trading",
        )


def test_repository_rejects_empty_process_name(
    tmp_path: Path,
) -> None:
    """空の処理名を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    with pytest.raises(
        ValueError,
        match="処理名",
    ):
        repository.has_completed(
            trading_date=TRADING_DATE,
            process_name=" ",
        )


def test_repository_rejects_naive_completed_at(
    tmp_path: Path,
) -> None:
    """タイムゾーンなし完了日時を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        repository.mark_completed(
            trading_date=TRADING_DATE,
            process_name="paper-trading",
            completed_at=datetime(
                2026,
                7,
                20,
                9,
                30,
            ),
        )


def test_repository_rejects_invalid_limit(
    tmp_path: Path,
) -> None:
    """0以下の取得件数を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    with pytest.raises(
        ValueError,
        match="取得件数",
    ):
        repository.list_recent(
            limit=0,
        )