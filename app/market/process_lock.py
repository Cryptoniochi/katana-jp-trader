"""自動更新処理の多重起動を防止するプロセスロック。"""

import json
import os
import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


LOCK_VERSION = 1
DEFAULT_STALE_AFTER_SECONDS = 60 * 60


@dataclass(frozen=True, slots=True)
class ProcessLockInfo:
    """ロックを取得したプロセスの情報。"""

    lock_version: int
    lock_id: str
    pid: int
    hostname: str
    process_name: str
    acquired_at: datetime

    def __post_init__(self) -> None:
        """ロック情報を検証する。"""

        if self.lock_version != LOCK_VERSION:
            raise ValueError(
                "未対応のプロセスロックバージョンです。"
            )

        if not self.lock_id.strip():
            raise ValueError(
                "ロックIDを指定してください。"
            )

        if self.pid <= 0:
            raise ValueError(
                "プロセスIDは0より大きい必要があります。"
            )

        if not self.hostname.strip():
            raise ValueError(
                "ホスト名を指定してください。"
            )

        if not self.process_name.strip():
            raise ValueError(
                "プロセス名を指定してください。"
            )

        if self.acquired_at.tzinfo is None:
            raise ValueError(
                "ロック取得日時にはタイムゾーンが必要です。"
            )


class ProcessLockError(RuntimeError):
    """プロセスロック処理の基底例外。"""


class AlreadyLockedError(ProcessLockError):
    """別のプロセスがロックを保持していることを表す。"""

    def __init__(
        self,
        lock_path: Path,
        lock_info: ProcessLockInfo,
    ) -> None:
        """既存ロックの情報を保持する。"""

        self.lock_path = lock_path
        self.lock_info = lock_info

        super().__init__(
            "別のプロセスが実行中です。 "
            f"path={lock_path} "
            f"pid={lock_info.pid} "
            f"hostname={lock_info.hostname} "
            f"process_name={lock_info.process_name} "
            f"acquired_at={lock_info.acquired_at.isoformat()}"
        )


class ProcessLockCorruptedError(ProcessLockError):
    """ロックファイルの内容が壊れていることを表す。"""


class ProcessLockOwnershipError(ProcessLockError):
    """現在のプロセスが所有していないロックを表す。"""


class ProcessLock:
    """ファイルを使用して処理の多重起動を防止する。"""

    def __init__(
        self,
        file_path: Path,
        *,
        process_name: str = "project-katana",
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
        now_provider: Callable[[], datetime] | None = None,
        pid_provider: Callable[[], int] = os.getpid,
        hostname_provider: Callable[[], str] = socket.gethostname,
        lock_id_provider: Callable[[], str] | None = None,
    ) -> None:
        """ロックファイルと期限判定条件を設定する。"""

        normalized_process_name = process_name.strip()

        if not normalized_process_name:
            raise ValueError(
                "プロセス名を指定してください。"
            )

        if stale_after_seconds <= 0:
            raise ValueError(
                "ロック有効秒数は0より大きい必要があります。"
            )

        self.file_path = file_path
        self.process_name = normalized_process_name
        self.stale_after_seconds = stale_after_seconds

        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self.pid_provider = pid_provider
        self.hostname_provider = hostname_provider
        self.lock_id_provider = (
            lock_id_provider
            if lock_id_provider is not None
            else lambda: uuid4().hex
        )

        self._owned_lock_info: ProcessLockInfo | None = None

    @property
    def is_acquired(self) -> bool:
        """現在のインスタンスがロックを所有しているか返す。"""

        return self._owned_lock_info is not None

    @property
    def lock_info(self) -> ProcessLockInfo | None:
        """現在所有しているロック情報を返す。"""

        return self._owned_lock_info

    def acquire(self) -> ProcessLockInfo:
        """ロックを排他的に取得する。"""

        if self.is_acquired:
            raise ProcessLockError(
                "このProcessLockは既にロックを取得しています。"
            )

        if self.file_path.exists() and self.file_path.is_dir():
            raise ProcessLockError(
                "プロセスロックのパスが"
                "ディレクトリになっています。 "
                f"path={self.file_path}"
            )

        self.file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        for _attempt_number in range(3):
            lock_info = self._create_lock_info()

            try:
                self._create_lock_file(lock_info)

            except FileExistsError:
                if self._recover_stale_lock():
                    continue

                existing_info = self._read_lock_info()

                raise AlreadyLockedError(
                    lock_path=self.file_path,
                    lock_info=existing_info,
                )

            self._owned_lock_info = lock_info

            return lock_info

        raise ProcessLockError(
            "プロセスロックを取得できませんでした。 "
            f"path={self.file_path}"
        )

    def release(self) -> None:
        """現在所有しているロックを解放する。"""

        owned_info = self._owned_lock_info

        if owned_info is None:
            return

        if not self.file_path.exists():
            self._owned_lock_info = None
            return

        current_info = self._read_lock_info()

        if current_info.lock_id != owned_info.lock_id:
            raise ProcessLockOwnershipError(
                "所有していないプロセスロックは"
                "削除できません。 "
                f"path={self.file_path} "
                f"owned_lock_id={owned_info.lock_id} "
                f"current_lock_id={current_info.lock_id}"
            )

        try:
            self.file_path.unlink()

        except OSError as error:
            raise ProcessLockError(
                "プロセスロックを解放できませんでした。 "
                f"path={self.file_path}"
            ) from error

        self._owned_lock_info = None

    def __enter__(self) -> ProcessLock:
        """with文の開始時にロックを取得する。"""

        self.acquire()

        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object | None,
    ) -> bool:
        """with文の終了時にロックを解放する。"""

        del exception_type
        del exception
        del traceback

        self.release()

        return False

    def _create_lock_info(self) -> ProcessLockInfo:
        """現在のプロセス情報からロック情報を作成する。"""

        current_time = self._current_time()

        return ProcessLockInfo(
            lock_version=LOCK_VERSION,
            lock_id=self.lock_id_provider().strip(),
            pid=self.pid_provider(),
            hostname=self.hostname_provider().strip(),
            process_name=self.process_name,
            acquired_at=current_time,
        )

    def _create_lock_file(
        self,
        lock_info: ProcessLockInfo,
    ) -> None:
        """ロックファイルを排他的に新規作成する。"""

        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
        )

        file_descriptor = os.open(
            self.file_path,
            flags,
            0o600,
        )

        try:
            serialized = json.dumps(
                self._serialize(lock_info),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )

            with os.fdopen(
                file_descriptor,
                mode="w",
                encoding="utf-8",
                newline="\n",
            ) as lock_file:
                lock_file.write(serialized)
                lock_file.write("\n")
                lock_file.flush()
                os.fsync(lock_file.fileno())

        except Exception:
            try:
                self.file_path.unlink(
                    missing_ok=True
                )
            except OSError:
                pass

            raise

    def _recover_stale_lock(self) -> bool:
        """期限切れロックなら安全に削除してTrueを返す。"""

        try:
            lock_info = self._read_lock_info()

        except ProcessLockCorruptedError:
            if not self._is_file_timestamp_stale():
                raise

            return self._remove_stale_lock()

        if not self._is_lock_info_stale(lock_info):
            return False

        return self._remove_stale_lock()

    def _remove_stale_lock(self) -> bool:
        """期限切れと判定したロックファイルを削除する。"""

        try:
            self.file_path.unlink()

        except FileNotFoundError:
            return True

        except OSError as error:
            raise ProcessLockError(
                "期限切れプロセスロックを"
                "削除できませんでした。 "
                f"path={self.file_path}"
            ) from error

        return True

    def _is_lock_info_stale(
        self,
        lock_info: ProcessLockInfo,
    ) -> bool:
        """ロック情報の取得日時が期限切れか返す。"""

        age_seconds = (
            self._current_time()
            - lock_info.acquired_at.astimezone(timezone.utc)
        ).total_seconds()

        return age_seconds >= self.stale_after_seconds

    def _is_file_timestamp_stale(self) -> bool:
        """壊れたロックを更新時刻から期限切れ判定する。"""

        try:
            modified_at = datetime.fromtimestamp(
                self.file_path.stat().st_mtime,
                tz=timezone.utc,
            )

        except OSError as error:
            raise ProcessLockError(
                "プロセスロックの更新日時を"
                "取得できませんでした。 "
                f"path={self.file_path}"
            ) from error

        age_seconds = (
            self._current_time()
            - modified_at
        ).total_seconds()

        return age_seconds >= self.stale_after_seconds

    def _read_lock_info(self) -> ProcessLockInfo:
        """ロックファイルを読み込み、内容を検証する。"""

        try:
            raw_text = self.file_path.read_text(
                encoding="utf-8"
            )
            raw_data = json.loads(raw_text)

        except FileNotFoundError as error:
            raise ProcessLockError(
                "プロセスロックが存在しません。 "
                f"path={self.file_path}"
            ) from error

        except (
            OSError,
            json.JSONDecodeError,
        ) as error:
            raise ProcessLockCorruptedError(
                "プロセスロックファイルを"
                "読み込めませんでした。 "
                f"path={self.file_path}"
            ) from error

        try:
            return self._deserialize(raw_data)

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise ProcessLockCorruptedError(
                "プロセスロックファイルの"
                "内容が不正です。 "
                f"path={self.file_path}"
            ) from error

    def _current_time(self) -> datetime:
        """UTCの現在日時を返す。"""

        current_time = self.now_provider()

        if current_time.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current_time.astimezone(
            timezone.utc
        )

    @staticmethod
    def _serialize(
        lock_info: ProcessLockInfo,
    ) -> dict[str, Any]:
        """ロック情報をJSON互換形式へ変換する。"""

        return {
            "lock_version": lock_info.lock_version,
            "lock_id": lock_info.lock_id,
            "pid": lock_info.pid,
            "hostname": lock_info.hostname,
            "process_name": lock_info.process_name,
            "acquired_at": (
                lock_info.acquired_at.isoformat()
            ),
        }

    @staticmethod
    def _deserialize(
        raw_data: object,
    ) -> ProcessLockInfo:
        """JSON互換形式からロック情報を復元する。"""

        if not isinstance(raw_data, dict):
            raise TypeError(
                "ロック情報は辞書形式である必要があります。"
            )

        acquired_at = datetime.fromisoformat(
            str(raw_data["acquired_at"])
        )

        return ProcessLockInfo(
            lock_version=int(
                raw_data["lock_version"]
            ),
            lock_id=str(
                raw_data["lock_id"]
            ),
            pid=int(
                raw_data["pid"]
            ),
            hostname=str(
                raw_data["hostname"]
            ),
            process_name=str(
                raw_data["process_name"]
            ),
            acquired_at=acquired_at,
        )