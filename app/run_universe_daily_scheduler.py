"""Universe Daily Scheduler CLI。"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import signal
import sys
from pathlib import Path

from app.runtime.universe_daily_scheduler import (
    UniverseDailyScheduler,
)


DEFAULT_LOCK_PATH = Path(
    "reports/service/universe_daily_scheduler.lock"
)

_WINDOWS_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_WINDOWS_STILL_ACTIVE = 259


class SchedulerAlreadyRunningError(RuntimeError):
    """Universe Daily Schedulerが既に稼働中。"""


class UniverseDailySchedulerLock:
    """PIDファイルを使ってSchedulerの多重起動を防止する。"""

    def __init__(self, path: Path = DEFAULT_LOCK_PATH) -> None:
        self.path = Path(path)
        self.acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        while True:
            try:
                descriptor = os.open(
                    self.path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                owner_pid = self._read_owner_pid()
                if (
                    owner_pid is not None
                    and self._pid_is_running(owner_pid)
                ):
                    raise SchedulerAlreadyRunningError(
                        "Universe Daily Scheduler is already running. "
                        f"pid={owner_pid} lock={self.path}"
                    )

                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                continue

            payload = {"pid": os.getpid()}
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
            self.acquired = True
            return

    def release(self) -> None:
        if not self.acquired:
            return

        owner_pid = self._read_owner_pid()
        if owner_pid == os.getpid():
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass

        self.acquired = False

    def _read_owner_pid(self) -> int | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return int(payload.get("pid"))
        except (
            OSError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return None

    @staticmethod
    def _pid_is_running(pid: int) -> bool:
        if pid <= 0:
            return False

        if pid == os.getpid():
            return True

        if sys.platform == "win32":
            return UniverseDailySchedulerLock._windows_pid_is_running(pid)

        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    @staticmethod
    def _windows_pid_is_running(pid: int) -> bool:
        """Windows APIでPIDが現在も生存しているか確認する。"""

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        open_process = kernel32.OpenProcess
        open_process.argtypes = [
            ctypes.c_uint32,
            ctypes.c_int,
            ctypes.c_uint32,
        ]
        open_process.restype = ctypes.c_void_p

        get_exit_code_process = kernel32.GetExitCodeProcess
        get_exit_code_process.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        get_exit_code_process.restype = ctypes.c_int

        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [ctypes.c_void_p]
        close_handle.restype = ctypes.c_int

        handle = open_process(
            _WINDOWS_PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            pid,
        )

        if not handle:
            error_code = ctypes.get_last_error()
            access_denied = 5
            return error_code == access_denied

        try:
            exit_code = ctypes.c_uint32()
            succeeded = get_exit_code_process(
                handle,
                ctypes.byref(exit_code),
            )
            if not succeeded:
                return True

            return exit_code.value == _WINDOWS_STILL_ACTIVE
        finally:
            close_handle(handle)

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.release()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--lock-path",
        type=Path,
        default=DEFAULT_LOCK_PATH,
    )
    return parser


def run(arguments=None) -> int:
    parsed = build_argument_parser().parse_args(arguments)

    lock = (
        None
        if parsed.once
        else UniverseDailySchedulerLock(parsed.lock_path)
    )

    if lock is not None:
        try:
            lock.acquire()
        except SchedulerAlreadyRunningError as error:
            print(str(error))
            return 2

    try:
        scheduler = UniverseDailyScheduler(
            enabled=parsed.enable,
            database_path=parsed.database_path,
        )

        def stop(_signum, _frame) -> None:
            scheduler.request_stop()

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)

        if parsed.once:
            status = scheduler.run_once()
            print(status.to_dict())
            return 0 if status.state.value not in {"failed"} else 1

        scheduler.run_forever()
        return 0
    finally:
        if lock is not None:
            lock.release()


if __name__ == "__main__":
    raise SystemExit(run())
