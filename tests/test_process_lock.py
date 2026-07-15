"""プロセスロックによる多重起動防止のテスト。"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.market.process_lock import (
    AlreadyLockedError,
    LOCK_VERSION,
    ProcessLock,
    ProcessLockCorruptedError,
    ProcessLockError,
    ProcessLockOwnershipError,
)


BASE_TIME = datetime(
    2026,
    7,
    16,
    0,
    0,
    tzinfo=timezone.utc,
)


def create_lock(
    file_path: Path,
    *,
    current_time: datetime = BASE_TIME,
    lock_id: str = "test-lock-id",
    stale_after_seconds: float = 3600,
) -> ProcessLock:
    """固定情報を使用するテスト用ロックを作成する。"""

    return ProcessLock(
        file_path=file_path,
        process_name="katana-test",
        stale_after_seconds=stale_after_seconds,
        now_provider=lambda: current_time,
        pid_provider=lambda: 12345,
        hostname_provider=lambda: "test-host",
        lock_id_provider=lambda: lock_id,
    )


def write_lock_file(
    file_path: Path,
    *,
    lock_id: str,
    acquired_at: datetime,
) -> None:
    """テスト用の有効なロックファイルを保存する。"""

    file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_path.write_text(
        json.dumps(
            {
                "lock_version": LOCK_VERSION,
                "lock_id": lock_id,
                "pid": 99999,
                "hostname": "other-host",
                "process_name": "other-process",
                "acquired_at": (
                    acquired_at.isoformat()
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_process_lock_acquires_and_writes_information(
    tmp_path: Path,
) -> None:
    """ロック取得時にプロセス情報を保存する。"""

    lock_path = (
        tmp_path / "locks" / "update.lock"
    )
    process_lock = create_lock(
        lock_path
    )

    lock_info = process_lock.acquire()

    assert process_lock.is_acquired is True
    assert process_lock.lock_info == lock_info
    assert lock_path.exists()

    raw_data = json.loads(
        lock_path.read_text(
            encoding="utf-8"
        )
    )

    assert raw_data["lock_version"] == (
        LOCK_VERSION
    )
    assert raw_data["lock_id"] == (
        "test-lock-id"
    )
    assert raw_data["pid"] == 12345
    assert raw_data["hostname"] == "test-host"
    assert raw_data["process_name"] == (
        "katana-test"
    )
    assert raw_data["acquired_at"] == (
        BASE_TIME.isoformat()
    )

    process_lock.release()

    assert lock_path.exists() is False
    assert process_lock.is_acquired is False


def test_process_lock_rejects_second_process(
    tmp_path: Path,
) -> None:
    """有効なロックがある場合は二重取得を拒否する。"""

    lock_path = tmp_path / "update.lock"

    first_lock = create_lock(
        lock_path,
        lock_id="first-lock",
    )
    first_lock.acquire()

    second_lock = create_lock(
        lock_path,
        lock_id="second-lock",
    )

    with pytest.raises(
        AlreadyLockedError,
        match="別のプロセス",
    ) as error_info:
        second_lock.acquire()

    assert error_info.value.lock_info.lock_id == (
        "first-lock"
    )
    assert second_lock.is_acquired is False

    first_lock.release()


def test_process_lock_context_manager_releases_lock(
    tmp_path: Path,
) -> None:
    """with文終了時にロックを削除する。"""

    lock_path = tmp_path / "update.lock"

    with create_lock(lock_path) as process_lock:
        assert process_lock.is_acquired is True
        assert lock_path.exists()

    assert process_lock.is_acquired is False
    assert lock_path.exists() is False


def test_process_lock_releases_lock_after_exception(
    tmp_path: Path,
) -> None:
    """with文内で例外が発生してもロックを削除する。"""

    lock_path = tmp_path / "update.lock"

    with pytest.raises(
        RuntimeError,
        match="test failure",
    ):
        with create_lock(lock_path):
            raise RuntimeError(
                "test failure"
            )

    assert lock_path.exists() is False


def test_process_lock_recovers_stale_lock(
    tmp_path: Path,
) -> None:
    """期限切れの有効なロックを回収して取得する。"""

    lock_path = tmp_path / "update.lock"

    write_lock_file(
        lock_path,
        lock_id="stale-lock",
        acquired_at=(
            BASE_TIME
            - timedelta(seconds=3600)
        ),
    )

    process_lock = create_lock(
        lock_path,
        lock_id="new-lock",
        stale_after_seconds=3600,
    )

    lock_info = process_lock.acquire()

    assert lock_info.lock_id == "new-lock"

    raw_data = json.loads(
        lock_path.read_text(
            encoding="utf-8"
        )
    )

    assert raw_data["lock_id"] == "new-lock"

    process_lock.release()


def test_process_lock_does_not_recover_fresh_lock(
    tmp_path: Path,
) -> None:
    """期限内のロックは削除しない。"""

    lock_path = tmp_path / "update.lock"

    write_lock_file(
        lock_path,
        lock_id="fresh-lock",
        acquired_at=(
            BASE_TIME
            - timedelta(seconds=3599)
        ),
    )

    process_lock = create_lock(
        lock_path,
        lock_id="new-lock",
        stale_after_seconds=3600,
    )

    with pytest.raises(
        AlreadyLockedError,
    ):
        process_lock.acquire()

    raw_data = json.loads(
        lock_path.read_text(
            encoding="utf-8"
        )
    )

    assert raw_data["lock_id"] == "fresh-lock"


def test_process_lock_rejects_fresh_corrupted_lock(
    tmp_path: Path,
) -> None:
    """新しい破損ロックは安全のため自動削除しない。"""

    lock_path = tmp_path / "update.lock"

    lock_path.write_text(
        "{invalid json",
        encoding="utf-8",
    )

    current_timestamp = BASE_TIME.timestamp()

    os.utime(
        lock_path,
        (
            current_timestamp,
            current_timestamp,
        ),
    )

    process_lock = create_lock(
        lock_path,
        stale_after_seconds=3600,
    )

    with pytest.raises(
        ProcessLockCorruptedError,
        match="読み込めません",
    ):
        process_lock.acquire()

    assert lock_path.exists()


def test_process_lock_recovers_stale_corrupted_lock(
    tmp_path: Path,
) -> None:
    """期限切れの破損ロックを更新時刻から回収する。"""

    lock_path = tmp_path / "update.lock"

    lock_path.write_text(
        "{invalid json",
        encoding="utf-8",
    )

    stale_timestamp = (
        BASE_TIME
        - timedelta(seconds=3600)
    ).timestamp()

    os.utime(
        lock_path,
        (
            stale_timestamp,
            stale_timestamp,
        ),
    )

    process_lock = create_lock(
        lock_path,
        lock_id="recovered-lock",
        stale_after_seconds=3600,
    )

    lock_info = process_lock.acquire()

    assert lock_info.lock_id == (
        "recovered-lock"
    )

    process_lock.release()

    assert lock_path.exists() is False


def test_process_lock_rejects_directory_path(
    tmp_path: Path,
) -> None:
    """ロックパスがディレクトリなら取得を拒否する。"""

    lock_path = tmp_path / "update.lock"
    lock_path.mkdir()

    process_lock = create_lock(
        lock_path
    )

    with pytest.raises(
        ProcessLockError,
        match="ディレクトリ",
    ):
        process_lock.acquire()


def test_process_lock_release_is_idempotent(
    tmp_path: Path,
) -> None:
    """未取得または解放済みロックの解放を許容する。"""

    lock_path = tmp_path / "update.lock"
    process_lock = create_lock(
        lock_path
    )

    process_lock.release()

    process_lock.acquire()
    process_lock.release()
    process_lock.release()

    assert process_lock.is_acquired is False
    assert lock_path.exists() is False


def test_process_lock_rejects_replaced_lock_on_release(
    tmp_path: Path,
) -> None:
    """所有中に置換された別ロックを削除しない。"""

    lock_path = tmp_path / "update.lock"

    process_lock = create_lock(
        lock_path,
        lock_id="owned-lock",
    )
    process_lock.acquire()

    write_lock_file(
        lock_path,
        lock_id="replacement-lock",
        acquired_at=BASE_TIME,
    )

    with pytest.raises(
        ProcessLockOwnershipError,
        match="所有していない",
    ):
        process_lock.release()

    assert lock_path.exists()

    raw_data = json.loads(
        lock_path.read_text(
            encoding="utf-8"
        )
    )

    assert raw_data["lock_id"] == (
        "replacement-lock"
    )


def test_process_lock_can_be_acquired_again_after_release(
    tmp_path: Path,
) -> None:
    """解放後は同じインスタンスで再取得できる。"""

    lock_path = tmp_path / "update.lock"
    lock_ids = iter(
        [
            "first-lock",
            "second-lock",
        ]
    )

    process_lock = ProcessLock(
        file_path=lock_path,
        process_name="katana-test",
        stale_after_seconds=3600,
        now_provider=lambda: BASE_TIME,
        pid_provider=lambda: 12345,
        hostname_provider=lambda: "test-host",
        lock_id_provider=lambda: next(lock_ids),
    )

    first_info = process_lock.acquire()
    process_lock.release()

    second_info = process_lock.acquire()

    assert first_info.lock_id == "first-lock"
    assert second_info.lock_id == "second-lock"

    process_lock.release()


@pytest.mark.parametrize(
    (
        "process_name",
        "stale_after_seconds",
        "message",
    ),
    [
        (
            "",
            3600,
            "プロセス名",
        ),
        (
            "katana-test",
            0,
            "ロック有効秒数",
        ),
        (
            "katana-test",
            -1,
            "ロック有効秒数",
        ),
    ],
)
def test_process_lock_rejects_invalid_arguments(
    tmp_path: Path,
    process_name: str,
    stale_after_seconds: float,
    message: str,
) -> None:
    """不正な初期化条件を拒否する。"""

    with pytest.raises(
        ValueError,
        match=message,
    ):
        ProcessLock(
            file_path=(
                tmp_path / "update.lock"
            ),
            process_name=process_name,
            stale_after_seconds=(
                stale_after_seconds
            ),
        )