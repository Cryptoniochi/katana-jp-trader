"""履歴取込の再開状態をテストする。"""

import json
from datetime import date
from pathlib import Path

import pytest

from app.market.history_state import (
    HistoryImportState,
    HistoryStateError,
    HistoryStateRepository,
    HistoryTaskKey,
)


def create_key(
    code: str = "7203",
    start_day: int = 1,
    end_day: int = 5,
) -> HistoryTaskKey:
    """テスト用チャンクキーを作成する。"""

    return HistoryTaskKey(
        code=code,
        start_date=date(
            2026,
            7,
            start_day,
        ),
        end_date=date(
            2026,
            7,
            end_day,
        ),
    )


def test_empty_state_has_no_completed_tasks() -> None:
    """空の状態は完了チャンクを持たない。"""

    state = HistoryImportState.empty()
    key = create_key()

    assert not state.is_completed(key)
    assert state.completed_task_keys == frozenset()
    assert state.failures == ()


def test_state_marks_task_completed() -> None:
    """指定チャンクを完了済みにできる。"""

    key = create_key()

    state = HistoryImportState.empty().mark_completed(key)

    assert state.is_completed(key)
    assert key.value in state.completed_task_keys


def test_mark_completed_removes_old_failure() -> None:
    """完了したチャンクの失敗情報を削除する。"""

    key = create_key()

    state = (
        HistoryImportState.empty()
        .mark_failed(
            key,
            message="temporary",
            attempt_count=3,
        )
        .mark_completed(key)
    )

    assert state.is_completed(key)
    assert state.failures == ()


def test_state_marks_task_failed() -> None:
    """チャンク失敗の内容を記録する。"""

    key = create_key()

    state = HistoryImportState.empty().mark_failed(
        key,
        message="API error",
        attempt_count=3,
    )

    assert len(state.failures) == 1

    failure = state.failures[0]

    assert failure.key == key
    assert failure.message == "API error"
    assert failure.attempt_count == 3


def test_mark_failed_replaces_same_task_failure() -> None:
    """同じチャンクの失敗情報を更新する。"""

    key = create_key()

    state = (
        HistoryImportState.empty()
        .mark_failed(
            key,
            message="first",
            attempt_count=1,
        )
        .mark_failed(
            key,
            message="second",
            attempt_count=3,
        )
    )

    assert len(state.failures) == 1
    assert state.failures[0].message == "second"
    assert state.failures[0].attempt_count == 3


def test_repository_saves_and_loads_state(
    tmp_path: Path,
) -> None:
    """状態をJSONへ保存して復元できる。"""

    file_path = tmp_path / "history_state.json"
    repository = HistoryStateRepository(file_path)

    completed_key = create_key(
        code="7203",
        start_day=1,
        end_day=5,
    )
    failed_key = create_key(
        code="8306",
        start_day=6,
        end_day=10,
    )

    state = (
        HistoryImportState.empty()
        .mark_completed(completed_key)
        .mark_failed(
            failed_key,
            message="timeout",
            attempt_count=3,
        )
    )

    output_path = repository.save(state)
    loaded = repository.load()

    assert output_path == file_path
    assert loaded.is_completed(completed_key)

    assert len(loaded.failures) == 1
    assert loaded.failures[0].key == failed_key
    assert loaded.failures[0].message == "timeout"
    assert loaded.failures[0].attempt_count == 3


def test_repository_returns_empty_state_without_file(
    tmp_path: Path,
) -> None:
    """状態ファイルがなければ空の状態を返す。"""

    repository = HistoryStateRepository(tmp_path / "missing.json")

    loaded = repository.load()

    assert loaded.completed_task_keys == frozenset()
    assert loaded.failures == ()


def test_repository_resets_state(
    tmp_path: Path,
) -> None:
    """状態ファイルを削除できる。"""

    file_path = tmp_path / "history_state.json"
    repository = HistoryStateRepository(file_path)

    repository.save(HistoryImportState.empty())

    assert file_path.exists()

    repository.reset()

    assert not file_path.exists()


def test_repository_rejects_invalid_json(
    tmp_path: Path,
) -> None:
    """不正なJSONを拒否する。"""

    file_path = tmp_path / "history_state.json"
    file_path.write_text(
        "{ invalid json",
        encoding="utf-8",
    )

    repository = HistoryStateRepository(file_path)

    with pytest.raises(
        HistoryStateError,
        match="読み込めません",
    ):
        repository.load()


def test_repository_rejects_unknown_version(
    tmp_path: Path,
) -> None:
    """未対応の状態バージョンを拒否する。"""

    file_path = tmp_path / "history_state.json"

    file_path.write_text(
        json.dumps(
            {
                "state_version": 999,
                "updated_at": ("2026-07-15T12:00:00"),
                "completed_task_keys": [],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    repository = HistoryStateRepository(file_path)

    with pytest.raises(
        HistoryStateError,
        match="内容が不正",
    ):
        repository.load()


def test_task_key_rejects_reversed_dates() -> None:
    """開始日が終了日より後のキーを拒否する。"""

    with pytest.raises(
        ValueError,
        match="開始日",
    ):
        HistoryTaskKey(
            code="7203",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 1),
        )
