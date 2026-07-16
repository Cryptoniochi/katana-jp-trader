"""J-Quants自動更新実行履歴Repositoryのテスト。"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.database import (
    SCHEMA_VERSION,
    initialize_database,
)
from app.monitoring.update_run_repository import (
    UpdateRunAlreadyFinishedError,
    UpdateRunMetrics,
    UpdateRunNotFoundError,
    UpdateRunRepository,
    UpdateRunRepositoryError,
    UpdateRunStatus,
)


START_TIME = datetime(
    2026,
    7,
    16,
    0,
    0,
    tzinfo=timezone.utc,
)

END_TIME = START_TIME + timedelta(
    seconds=12.5,
)


def create_repository(
    tmp_path: Path,
    *,
    times: list[datetime] | None = None,
    run_ids: list[str] | None = None,
) -> tuple[Path, UpdateRunRepository]:
    """初期化済みDBと実行履歴Repositoryを作成する。"""

    database_path = tmp_path / "katana.db"

    initialize_database(
        database_path,
    )

    resolved_times = iter(
        times or [START_TIME],
    )
    resolved_run_ids = iter(
        run_ids or ["run-001"],
    )

    repository = UpdateRunRepository(
        database_path,
        now_provider=lambda: next(
            resolved_times,
        ),
        run_id_provider=lambda: next(
            resolved_run_ids,
        ),
    )

    return database_path, repository


def create_metrics() -> UpdateRunMetrics:
    """成功した自動更新の件数情報を作成する。"""

    return UpdateRunMetrics(
        requested_code_count=3,
        updated_code_count=2,
        skipped_code_count=1,
        failed_code_count=0,
        business_date_count=4,
        request_count=8,
        successful_request_count=6,
        empty_request_count=2,
        failed_request_count=0,
        processed_bar_count=360,
    )


def test_initialize_database_creates_update_runs_table(
    tmp_path: Path,
) -> None:
    """DB初期化でupdate_runsテーブルを作成する。"""

    database_path = tmp_path / "katana.db"

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
              AND name = 'update_runs'
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
        "update_runs",
    )
    assert version_row == (
        SCHEMA_VERSION,
    )
    assert SCHEMA_VERSION == 7


def test_initialize_database_is_idempotent(
    tmp_path: Path,
) -> None:
    """DB初期化を複数回実行しても成功する。"""

    database_path = tmp_path / "katana.db"

    initialize_database(
        database_path,
    )
    initialize_database(
        database_path,
    )

    with sqlite3.connect(
        database_path,
    ) as connection:
        table_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'update_runs'
            """
        ).fetchone()

    assert table_count == (
        1,
    )


def test_repository_starts_run(
    tmp_path: Path,
) -> None:
    """自動更新実行をrunning状態で保存する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    record = repository.start(
        process_name="jquants-update",
        requested_code_count=3,
    )

    assert record.id > 0
    assert record.run_id == "run-001"
    assert record.process_name == "jquants-update"
    assert record.status is UpdateRunStatus.RUNNING
    assert record.started_at == START_TIME
    assert record.finished_at is None
    assert record.exit_code is None
    assert record.metrics.requested_code_count == 3
    assert record.is_finished is False
    assert record.duration_seconds is None

    loaded = repository.get(
        "run-001",
    )

    assert loaded == record


def test_repository_finishes_successful_run(
    tmp_path: Path,
) -> None:
    """成功した実行を終了状態へ更新する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            START_TIME,
            END_TIME,
        ],
    )

    repository.start(
        process_name="jquants-update",
        requested_code_count=3,
    )

    finished = repository.finish(
        "run-001",
        status=UpdateRunStatus.SUCCESS,
        exit_code=0,
        metrics=create_metrics(),
    )

    assert finished.status is UpdateRunStatus.SUCCESS
    assert finished.exit_code == 0
    assert finished.finished_at == END_TIME
    assert finished.is_finished is True
    assert finished.duration_seconds == pytest.approx(
        12.5,
    )
    assert finished.metrics.updated_code_count == 2
    assert finished.metrics.skipped_code_count == 1
    assert finished.metrics.processed_bar_count == 360
    assert finished.error_message is None


def test_repository_saves_partial_failure(
    tmp_path: Path,
) -> None:
    """部分失敗結果とメッセージを保存する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            START_TIME,
            END_TIME,
        ],
    )

    repository.start(
        process_name="jquants-update",
        requested_code_count=2,
    )

    metrics = UpdateRunMetrics(
        requested_code_count=2,
        updated_code_count=1,
        skipped_code_count=0,
        failed_code_count=1,
        business_date_count=2,
        request_count=2,
        successful_request_count=1,
        empty_request_count=0,
        failed_request_count=1,
        processed_bar_count=60,
    )

    finished = repository.finish(
        "run-001",
        status=UpdateRunStatus.PARTIAL_FAILURE,
        exit_code=1,
        metrics=metrics,
        error_message="one request failed",
    )

    assert finished.status is UpdateRunStatus.PARTIAL_FAILURE
    assert finished.exit_code == 1
    assert finished.metrics.failed_code_count == 1
    assert finished.metrics.failed_request_count == 1
    assert finished.error_message == "one request failed"


def test_repository_saves_execution_failure(
    tmp_path: Path,
) -> None:
    """実行エラーをfailed状態として保存する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            START_TIME,
            END_TIME,
        ],
    )

    repository.start(
        process_name="jquants-update",
        requested_code_count=3,
    )

    finished = repository.finish(
        "run-001",
        status=UpdateRunStatus.FAILED,
        exit_code=3,
        metrics=UpdateRunMetrics(
            requested_code_count=3,
        ),
        error_message="calendar unavailable",
    )

    assert finished.status is UpdateRunStatus.FAILED
    assert finished.exit_code == 3
    assert finished.error_message == "calendar unavailable"


def test_repository_returns_latest_run(
    tmp_path: Path,
) -> None:
    """開始日時が最新の実行履歴を返す。"""

    first_time = START_TIME
    second_time = START_TIME + timedelta(
        minutes=5,
    )

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            first_time,
            second_time,
        ],
        run_ids=[
            "run-001",
            "run-002",
        ],
    )

    repository.start(
        process_name="update",
        requested_code_count=1,
    )
    repository.start(
        process_name="update",
        requested_code_count=1,
    )

    latest = repository.latest()

    assert latest is not None
    assert latest.run_id == "run-002"
    assert latest.started_at == second_time


def test_repository_returns_none_without_runs(
    tmp_path: Path,
) -> None:
    """実行履歴がなければlatestはNoneを返す。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    assert repository.latest() is None
    assert repository.count() == 0


def test_repository_lists_recent_runs_in_descending_order(
    tmp_path: Path,
) -> None:
    """実行履歴を新しい順に返す。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            START_TIME,
            START_TIME + timedelta(
                minutes=1,
            ),
            START_TIME + timedelta(
                minutes=2,
            ),
        ],
        run_ids=[
            "run-001",
            "run-002",
            "run-003",
        ],
    )

    for _ in range(3):
        repository.start(
            process_name="update",
            requested_code_count=1,
        )

    records = repository.list_recent(
        limit=2,
    )

    assert [
        record.run_id
        for record in records
    ] == [
        "run-003",
        "run-002",
    ]


def test_repository_filters_by_status(
    tmp_path: Path,
) -> None:
    """ステータスを指定して実行履歴を取得する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            START_TIME,
            END_TIME,
            START_TIME + timedelta(
                minutes=1,
            ),
        ],
        run_ids=[
            "run-001",
            "run-002",
        ],
    )

    repository.start(
        process_name="update",
        requested_code_count=1,
    )

    repository.finish(
        "run-001",
        status=UpdateRunStatus.SUCCESS,
        exit_code=0,
        metrics=UpdateRunMetrics(
            requested_code_count=1,
            skipped_code_count=1,
        ),
    )

    repository.start(
        process_name="update",
        requested_code_count=1,
    )

    success_records = repository.list_recent(
        status=UpdateRunStatus.SUCCESS,
    )

    running_records = repository.list_recent(
        status=UpdateRunStatus.RUNNING,
    )

    assert [
        record.run_id
        for record in success_records
    ] == [
        "run-001",
    ]

    assert [
        record.run_id
        for record in running_records
    ] == [
        "run-002",
    ]

    assert repository.count(
        status=UpdateRunStatus.SUCCESS,
    ) == 1

    assert repository.count(
        status=UpdateRunStatus.RUNNING,
    ) == 1


def test_repository_rejects_duplicate_run_id(
    tmp_path: Path,
) -> None:
    """同じ実行IDの重複登録を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            START_TIME,
            START_TIME,
        ],
    )

    repository.start(
        process_name="update",
        requested_code_count=1,
        run_id="duplicate-run",
    )

    with pytest.raises(
        UpdateRunRepositoryError,
        match="既に存在",
    ):
        repository.start(
            process_name="update",
            requested_code_count=1,
            run_id="duplicate-run",
        )


def test_repository_rejects_missing_run(
    tmp_path: Path,
) -> None:
    """存在しない実行IDの取得を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    with pytest.raises(
        UpdateRunNotFoundError,
        match="存在しません",
    ):
        repository.get(
            "missing-run",
        )


def test_repository_rejects_second_finish(
    tmp_path: Path,
) -> None:
    """終了済み実行履歴の再終了を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            START_TIME,
            END_TIME,
        ],
    )

    repository.start(
        process_name="update",
        requested_code_count=1,
    )

    repository.finish(
        "run-001",
        status=UpdateRunStatus.SUCCESS,
        exit_code=0,
        metrics=UpdateRunMetrics(
            requested_code_count=1,
            skipped_code_count=1,
        ),
    )

    with pytest.raises(
        UpdateRunAlreadyFinishedError,
        match="終了済み",
    ):
        repository.finish(
            "run-001",
            status=UpdateRunStatus.FAILED,
            exit_code=3,
            metrics=UpdateRunMetrics(
                requested_code_count=1,
            ),
        )


def test_repository_rejects_running_finish_status(
    tmp_path: Path,
) -> None:
    """finishでrunning状態を指定することを拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    repository.start(
        process_name="update",
        requested_code_count=1,
    )

    with pytest.raises(
        ValueError,
        match="終了済みステータス",
    ):
        repository.finish(
            "run-001",
            status=UpdateRunStatus.RUNNING,
            exit_code=0,
            metrics=UpdateRunMetrics(
                requested_code_count=1,
            ),
        )


def test_repository_rejects_negative_exit_code(
    tmp_path: Path,
) -> None:
    """負の終了コードを拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    repository.start(
        process_name="update",
        requested_code_count=1,
    )

    with pytest.raises(
        ValueError,
        match="終了コード",
    ):
        repository.finish(
            "run-001",
            status=UpdateRunStatus.FAILED,
            exit_code=-1,
            metrics=UpdateRunMetrics(
                requested_code_count=1,
            ),
        )


def test_repository_rejects_end_before_start(
    tmp_path: Path,
) -> None:
    """開始日時より前の終了日時を拒否する。"""

    earlier_time = START_TIME - timedelta(
        seconds=1,
    )

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            START_TIME,
            earlier_time,
        ],
    )

    repository.start(
        process_name="update",
        requested_code_count=1,
    )

    with pytest.raises(
        ValueError,
        match="終了日時",
    ):
        repository.finish(
            "run-001",
            status=UpdateRunStatus.FAILED,
            exit_code=3,
            metrics=UpdateRunMetrics(
                requested_code_count=1,
            ),
        )


def test_repository_rejects_invalid_recent_limit(
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


def test_repository_rejects_empty_process_name(
    tmp_path: Path,
) -> None:
    """空のプロセス名を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    with pytest.raises(
        ValueError,
        match="プロセス名",
    ):
        repository.start(
            process_name=" ",
            requested_code_count=1,
        )


def test_repository_rejects_negative_requested_code_count(
    tmp_path: Path,
) -> None:
    """負の対象銘柄数を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    with pytest.raises(
        ValueError,
        match="対象銘柄数",
    ):
        repository.start(
            process_name="update",
            requested_code_count=-1,
        )


def test_repository_rejects_empty_run_id(
    tmp_path: Path,
) -> None:
    """空の実行IDを拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    with pytest.raises(
        ValueError,
        match="実行ID",
    ):
        repository.start(
            process_name="update",
            requested_code_count=1,
            run_id=" ",
        )


def test_update_run_metrics_rejects_negative_count() -> None:
    """負の件数を拒否する。"""

    with pytest.raises(
        ValueError,
        match="0以上",
    ):
        UpdateRunMetrics(
            requested_code_count=-1,
        )


def test_update_run_metrics_rejects_excess_code_count() -> None:
    """内訳銘柄数が対象銘柄数を超えることを拒否する。"""

    with pytest.raises(
        ValueError,
        match="対象銘柄数",
    ):
        UpdateRunMetrics(
            requested_code_count=1,
            updated_code_count=2,
        )


def test_update_run_metrics_rejects_excess_request_count() -> None:
    """内訳リクエスト数が総数を超えることを拒否する。"""

    with pytest.raises(
        ValueError,
        match="総リクエスト数",
    ):
        UpdateRunMetrics(
            requested_code_count=1,
            request_count=1,
            successful_request_count=2,
        )