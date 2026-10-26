"""Project KATANA Service external watchdog."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


DEFAULT_TASK_NAME = "Project KATANA Service"
DEFAULT_STATUS_PATH = Path("reports/service/katana_service_status.json")
DEFAULT_LOG_PATH = Path("logs/service/katana_service_watchdog.log")
DEFAULT_STALE_SECONDS = 90.0
DEFAULT_RECOVERY_WAIT_SECONDS = 45.0
DEFAULT_TASK_STOP_WAIT_SECONDS = 15.0

MANAGED_MODULES = (
    "app.run_katana_service_resilient",
    "app.run_katana_service",
    "app.dashboard",
    "app.run_dynamic_watchlist_scheduler",
    "app.run_universe_daily_scheduler",
    "app.run_high_breakout_scheduler",
    "app.run_morning_preflight_scheduler",
    "app.run_daily_report_scheduler",
    "app.run_scheduled_paper_trading",
)


@dataclass(frozen=True, slots=True)
class WatchdogResult:
    healthy: bool
    recovered: bool
    message: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_status(
    status_path: Path,
    *,
    stale_seconds: float,
    now: datetime | None = None,
) -> tuple[bool, bool]:
    """Return (fresh, healthy) for a syntactically valid service status."""
    if stale_seconds <= 0:
        raise ValueError("stale_seconds must be positive.")
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
        generated_at = datetime.fromisoformat(str(payload["generated_at"]))
        service_state = str(payload["service_state"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False, False

    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    current = now or _utc_now()
    age = (current - generated_at.astimezone(timezone.utc)).total_seconds()
    fresh = 0 <= age <= stale_seconds
    return fresh, service_state == "healthy"


def _status_is_fresh(
    status_path: Path,
    *,
    stale_seconds: float,
    now: datetime | None = None,
) -> bool:
    fresh, _healthy = _read_status(
        status_path,
        stale_seconds=stale_seconds,
        now=now,
    )
    return fresh


def _status_is_healthy(
    status_path: Path,
    *,
    stale_seconds: float,
    now: datetime | None = None,
) -> bool:
    fresh, healthy = _read_status(
        status_path,
        stale_seconds=stale_seconds,
        now=now,
    )
    return fresh and healthy


def _task_state(task_name: str) -> str | None:
    escaped = task_name.replace("'", "''")
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                f"(Get-ScheduledTask -TaskName '{escaped}' "
                "-ErrorAction Stop).State.ToString()"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="mbcs",
        errors="replace",
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _module_command_pattern(module: str) -> str:
    escaped = re.escape(module)
    return rf"(?i)(?:^|\s)-m\s+{escaped}(?:\s|$)"


def _list_katana_process_ids() -> list[int]:
    patterns = [_module_command_pattern(module) for module in MANAGED_MODULES]
    conditions = " -or ".join(
        "$_.CommandLine -match '" + pattern.replace("'", "''") + "'"
        for pattern in patterns
    )
    script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -match '^(python|pythonw)\\.exe$' "
        " -and $_.CommandLine -and ("
        + conditions
        + ") } | Select-Object -ExpandProperty ProcessId"
    )
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="mbcs",
        errors="replace",
    )
    if completed.returncode != 0:
        return []
    result: list[int] = []
    for line in completed.stdout.splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid != os.getpid():
            result.append(pid)
    return sorted(set(result))


def _kill_process_trees(process_ids: Sequence[int]) -> None:
    for pid in process_ids:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="replace",
        )


def _end_task(task_name: str) -> bool:
    completed = subprocess.run(
        ["schtasks", "/End", "/TN", task_name],
        check=False,
        capture_output=True,
        text=True,
        encoding="mbcs",
        errors="replace",
    )
    return completed.returncode == 0


def _start_task(task_name: str) -> bool:
    completed = subprocess.run(
        ["schtasks", "/Run", "/TN", task_name],
        check=False,
        capture_output=True,
        text=True,
        encoding="mbcs",
        errors="replace",
    )
    return completed.returncode == 0


def _append_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = _utc_now().isoformat()
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(f"{timestamp} {message}\n")


def _wait_for_task_not_running(
    task_name: str,
    *,
    timeout_seconds: float,
    sleep=time.sleep,
) -> bool:
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    while True:
        if _task_state(task_name) != "Running":
            return True
        if time.monotonic() >= deadline:
            return False
        sleep(1.0)


def check_and_recover(
    *,
    task_name: str = DEFAULT_TASK_NAME,
    status_path: Path = DEFAULT_STATUS_PATH,
    log_path: Path = DEFAULT_LOG_PATH,
    stale_seconds: float = DEFAULT_STALE_SECONDS,
    recovery_wait_seconds: float = DEFAULT_RECOVERY_WAIT_SECONDS,
    task_stop_wait_seconds: float = DEFAULT_TASK_STOP_WAIT_SECONDS,
    sleep=time.sleep,
) -> WatchdogResult:
    try:
        state = _task_state(task_name)
        fresh, status_healthy = _read_status(
            status_path,
            stale_seconds=stale_seconds,
        )

        if state == "Running" and fresh and status_healthy:
            return WatchdogResult(True, False, "Service is healthy.")

        _append_log(
            log_path,
            (
                "Recovery started. "
                f"task_state={state!r} "
                f"status_fresh={fresh} "
                f"status_healthy={status_healthy}"
            ),
        )

        # End the Scheduled Task wrapper first.  In the failure mode observed on
        # Windows, the wrapper and managed children can outlive each other.
        # Ending the task first avoids MultipleInstancesPolicy=IgnoreNew
        # rejecting the subsequent restart.
        _end_task(task_name)
        if not _wait_for_task_not_running(
            task_name,
            timeout_seconds=task_stop_wait_seconds,
            sleep=sleep,
        ):
            message = "Recovery failed: Scheduled Task did not stop."
            _append_log(log_path, message)
            return WatchdogResult(False, False, message)

        # /End is not sufficient: KATANA children have been observed to remain
        # orphaned.  Clean those known module processes after ending the task.
        process_ids = _list_katana_process_ids()
        _kill_process_trees(process_ids)

        if not _start_task(task_name):
            message = "Recovery failed: Scheduled Task could not be started."
            _append_log(log_path, message)
            return WatchdogResult(False, False, message)

        deadline = time.monotonic() + max(recovery_wait_seconds, 0.0)
        while True:
            if (
                _task_state(task_name) == "Running"
                and _status_is_healthy(
                    status_path,
                    stale_seconds=stale_seconds,
                )
            ):
                message = "Recovery completed successfully."
                _append_log(log_path, message)
                return WatchdogResult(True, True, message)
            if time.monotonic() >= deadline:
                break
            sleep(1.0)

        message = "Recovery timed out before Service became healthy."
        _append_log(log_path, message)
        return WatchdogResult(False, True, message)
    except Exception as exc:
        message = f"Recovery failed with {type(exc).__name__}: {exc}"
        try:
            _append_log(log_path, message)
        except Exception:
            pass
        return WatchdogResult(False, False, message)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KATANA Service watchdog")
    parser.add_argument("--task-name", default=DEFAULT_TASK_NAME)
    parser.add_argument("--status-path", type=Path, default=DEFAULT_STATUS_PATH)
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument(
        "--stale-seconds",
        type=float,
        default=DEFAULT_STALE_SECONDS,
    )
    parser.add_argument(
        "--recovery-wait-seconds",
        type=float,
        default=DEFAULT_RECOVERY_WAIT_SECONDS,
    )
    parser.add_argument(
        "--task-stop-wait-seconds",
        type=float,
        default=DEFAULT_TASK_STOP_WAIT_SECONDS,
    )
    return parser


def run(arguments: Sequence[str] | None = None) -> int:
    parsed = build_argument_parser().parse_args(arguments)
    result = check_and_recover(
        task_name=parsed.task_name,
        status_path=parsed.status_path,
        log_path=parsed.log_path,
        stale_seconds=parsed.stale_seconds,
        recovery_wait_seconds=parsed.recovery_wait_seconds,
        task_stop_wait_seconds=parsed.task_stop_wait_seconds,
    )
    print(result.message)
    return 0 if result.healthy else 1


if __name__ == "__main__":
    raise SystemExit(run())
