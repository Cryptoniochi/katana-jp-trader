"""KATANA Service Managerの常駐運用を堅牢化する。"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import BinaryIO

from app.runtime.katana_service_manager import (
    KatanaServiceManager,
)


class ServiceAlreadyRunningError(RuntimeError):
    """別のService Managerが既に稼働している。"""


class ServiceInstanceLock:
    """プロセス存続中だけ保持される排他ファイルロック。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._stream: BinaryIO | None = None

    def acquire(self) -> None:
        if self._stream is not None:
            return

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        stream = self.path.open("a+b")

        try:
            self._lock_stream(stream)
            stream.seek(0)
            stream.truncate()
            stream.write(
                f"{os.getpid()}\n".encode("ascii")
            )
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            stream.close()
            raise

        self._stream = stream

    def release(self) -> None:
        stream = self._stream

        if stream is None:
            return

        try:
            self._unlock_stream(stream)
        finally:
            stream.close()
            self._stream = None

    @staticmethod
    def _lock_stream(stream: BinaryIO) -> None:
        if os.name == "nt":
            import msvcrt

            stream.seek(0)
            try:
                msvcrt.locking(
                    stream.fileno(),
                    msvcrt.LK_NBLCK,
                    1,
                )
            except OSError as error:
                raise ServiceAlreadyRunningError(
                    "KATANA Service Managerは既に起動しています。"
                ) from error
            return

        import fcntl

        try:
            fcntl.flock(
                stream.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except OSError as error:
            raise ServiceAlreadyRunningError(
                "KATANA Service Managerは既に起動しています。"
            ) from error

    @staticmethod
    def _unlock_stream(stream: BinaryIO) -> None:
        if os.name == "nt":
            import msvcrt

            stream.seek(0)
            try:
                msvcrt.locking(
                    stream.fileno(),
                    msvcrt.LK_UNLCK,
                    1,
                )
            except OSError:
                pass
            return

        import fcntl

        try:
            fcntl.flock(
                stream.fileno(),
                fcntl.LOCK_UN,
            )
        except OSError:
            pass


class ResilientKatanaServiceManager(
    KatanaServiceManager
):
    """Status書込み障害で常駐Managerを停止させない。"""

    def __init__(
        self,
        *args,
        status_write_attempts: int = 5,
        status_write_retry_seconds: float = 0.1,
        diagnostic_log_path: Path | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        if status_write_attempts <= 0:
            raise ValueError(
                "Status書込み試行回数は1以上が必要です。"
            )

        if status_write_retry_seconds < 0:
            raise ValueError(
                "Status再試行間隔は0以上が必要です。"
            )

        self.status_write_attempts = (
            status_write_attempts
        )
        self.status_write_retry_seconds = (
            status_write_retry_seconds
        )
        self.diagnostic_log_path = (
            Path(diagnostic_log_path)
            if diagnostic_log_path is not None
            else self.status_path.parent
            / "katana_service_manager_errors.log"
        )

    def write_status(self) -> bool:
        """一意な一時ファイルで保存し、失敗時は診断ログへ退避する。"""

        self.status_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        payload = json.dumps(
            self.create_status().to_dict(),
            ensure_ascii=False,
            indent=2,
        )
        temporary_path = self.status_path.with_name(
            (
                f".{self.status_path.name}."
                f"{os.getpid()}."
                f"{threading.get_ident()}.tmp"
            )
        )
        last_error: OSError | None = None

        try:
            for attempt in range(
                1,
                self.status_write_attempts + 1,
            ):
                try:
                    temporary_path.write_text(
                        payload,
                        encoding="utf-8",
                    )
                    os.replace(
                        temporary_path,
                        self.status_path,
                    )
                    return True
                except OSError as error:
                    last_error = error

                    if (
                        attempt
                        < self.status_write_attempts
                        and self.status_write_retry_seconds > 0
                    ):
                        time.sleep(
                            self.status_write_retry_seconds
                        )
        finally:
            try:
                temporary_path.unlink(
                    missing_ok=True
                )
            except OSError:
                pass

        if last_error is not None:
            self._write_diagnostic(
                (
                    "Failed to write service status "
                    f"after {self.status_write_attempts} attempts."
                ),
                last_error,
            )

        return False

    def _write_diagnostic(
        self,
        message: str,
        error: BaseException,
    ) -> None:
        try:
            self.diagnostic_log_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            timestamp = (
                self._current_time().isoformat()
            )
            with self.diagnostic_log_path.open(
                "a",
                encoding="utf-8",
            ) as stream:
                stream.write(
                    f"{timestamp} {message} "
                    f"{type(error).__name__}: {error}\n"
                )
        except OSError:
            pass
