"""Dashboard常駐プロセスを待機・再起動付きで管理する。"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


DEFAULT_DATABASE_PATH = Path("data/katana.db")
DEFAULT_PORT = 8000
DEFAULT_HOST_MODE = "tailscale"
DEFAULT_TAILSCALE_WAIT_ATTEMPTS = 24
DEFAULT_TAILSCALE_WAIT_SECONDS = 5.0
DEFAULT_RESTART_DELAY_SECONDS = 5.0
DEFAULT_MAX_RESTARTS = 20


@dataclass(frozen=True, slots=True)
class DashboardResidentSettings:
    """Dashboard常駐起動設定。"""

    database_path: Path
    port: int = DEFAULT_PORT
    host_mode: str = DEFAULT_HOST_MODE
    log_level: str = "info"
    tailscale_wait_attempts: int = (
        DEFAULT_TAILSCALE_WAIT_ATTEMPTS
    )
    tailscale_wait_seconds: float = (
        DEFAULT_TAILSCALE_WAIT_SECONDS
    )
    restart_delay_seconds: float = (
        DEFAULT_RESTART_DELAY_SECONDS
    )
    max_restarts: int = DEFAULT_MAX_RESTARTS

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65_535:
            raise ValueError(
                "Portは1以上65535以下で指定してください。"
            )

        if self.host_mode not in {
            "tailscale",
            "local",
        }:
            raise ValueError(
                "host_modeはtailscaleまたはlocalです。"
            )

        if self.tailscale_wait_attempts <= 0:
            raise ValueError(
                "Tailscale待機回数は0より大きい必要があります。"
            )

        if self.tailscale_wait_seconds < 0:
            raise ValueError(
                "Tailscale待機間隔は0以上である必要があります。"
            )

        if self.restart_delay_seconds < 0:
            raise ValueError(
                "再起動待機時間は0以上である必要があります。"
            )

        if self.max_restarts < 0:
            raise ValueError(
                "最大再起動回数は0以上である必要があります。"
            )


class DashboardResidentLaunchError(RuntimeError):
    """Dashboard常駐起動に失敗したことを表す。"""


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Project KATANA Dashboardを待機・再起動付きで"
            "常駐実行します。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
    )
    parser.add_argument(
        "--host-mode",
        choices=("tailscale", "local"),
        default=DEFAULT_HOST_MODE,
    )
    parser.add_argument(
        "--log-level",
        choices=(
            "critical",
            "error",
            "warning",
            "info",
            "debug",
            "trace",
        ),
        default="info",
    )
    parser.add_argument(
        "--tailscale-wait-attempts",
        type=int,
        default=DEFAULT_TAILSCALE_WAIT_ATTEMPTS,
    )
    parser.add_argument(
        "--tailscale-wait-seconds",
        type=float,
        default=DEFAULT_TAILSCALE_WAIT_SECONDS,
    )
    parser.add_argument(
        "--restart-delay-seconds",
        type=float,
        default=DEFAULT_RESTART_DELAY_SECONDS,
    )
    parser.add_argument(
        "--max-restarts",
        type=int,
        default=DEFAULT_MAX_RESTARTS,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )
    return parser


def resolve_tailscale_executable() -> Path:
    """Tailscale CLIの実行ファイルを解決する。"""

    discovered = shutil.which("tailscale")

    if discovered:
        return Path(discovered)

    candidates = (
        Path(
            os.environ.get(
                "ProgramFiles",
                r"C:\Program Files",
            )
        )
        / "Tailscale"
        / "tailscale.exe",
        Path(
            os.environ.get(
                "LocalAppData",
                "",
            )
        )
        / "Tailscale"
        / "tailscale.exe",
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise DashboardResidentLaunchError(
        "Tailscale CLIが見つかりません。"
    )


def resolve_tailscale_ip(
    executable: Path | None = None,
) -> str:
    """PCのTailscale IPv4アドレスを取得する。"""

    command = [
        str(
            executable
            if executable is not None
            else resolve_tailscale_executable()
        ),
        "ip",
        "-4",
    ]

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if completed.returncode != 0:
        raise DashboardResidentLaunchError(
            "Tailscale IPv4アドレスを取得できません。 "
            f"stderr={completed.stderr.strip()}"
        )

    addresses = [
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip()
    ]

    if not addresses:
        raise DashboardResidentLaunchError(
            "Tailscale IPv4アドレスが空です。"
        )

    address = addresses[0]

    try:
        socket.inet_aton(address)
    except OSError as error:
        raise DashboardResidentLaunchError(
            "Tailscale IPv4アドレスが不正です。 "
            f"value={address}"
        ) from error

    return address


def wait_for_tailscale_ip(
    *,
    attempts: int,
    wait_seconds: float,
    resolver: Callable[[], str] = resolve_tailscale_ip,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Tailscale接続完了まで再試行してIPv4を返す。"""

    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            address = resolver()
            print(
                "Tailscale is ready. "
                f"address={address} attempt={attempt}"
            )
            return address
        except DashboardResidentLaunchError as error:
            last_error = error
            print(
                "Waiting for Tailscale. "
                f"attempt={attempt}/{attempts} "
                f"reason={error}"
            )

            if attempt < attempts:
                sleep(wait_seconds)

    raise DashboardResidentLaunchError(
        "Tailscale接続待機がタイムアウトしました。 "
        f"last_error={last_error}"
    )


def build_dashboard_command(
    *,
    settings: DashboardResidentSettings,
    host: str,
) -> list[str]:
    """Dashboard起動コマンドを組み立てる。"""

    return [
        sys.executable,
        "-m",
        "app.dashboard",
        "--host",
        host,
        "--port",
        str(settings.port),
        "--database",
        str(settings.database_path),
        "--no-browser",
        "--log-level",
        settings.log_level,
    ]


def run_dashboard_supervisor(
    *,
    settings: DashboardResidentSettings,
    host: str,
    runner: Callable[..., subprocess.CompletedProcess] = (
        subprocess.run
    ),
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Dashboard終了時に制限付きで再起動する。"""

    command = build_dashboard_command(
        settings=settings,
        host=host,
    )
    restart_count = 0

    while True:
        print(
            "Starting Dashboard process. "
            f"restart_count={restart_count}"
        )
        completed = runner(
            command,
            check=False,
            cwd=Path.cwd(),
        )
        exit_code = int(completed.returncode)

        if exit_code == 0:
            print(
                "Dashboard stopped normally. "
                "No restart is required."
            )
            return 0

        if restart_count >= settings.max_restarts:
            print(
                "Dashboard restart limit reached. "
                f"exit_code={exit_code}"
            )
            return exit_code

        restart_count += 1
        print(
            "Dashboard stopped unexpectedly. "
            f"exit_code={exit_code} "
            f"restart={restart_count}/"
            f"{settings.max_restarts}"
        )
        sleep(
            settings.restart_delay_seconds
        )


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    settings = DashboardResidentSettings(
        database_path=parsed.database_path,
        port=parsed.port,
        host_mode=parsed.host_mode,
        log_level=parsed.log_level,
        tailscale_wait_attempts=(
            parsed.tailscale_wait_attempts
        ),
        tailscale_wait_seconds=(
            parsed.tailscale_wait_seconds
        ),
        restart_delay_seconds=(
            parsed.restart_delay_seconds
        ),
        max_restarts=parsed.max_restarts,
    )

    host = (
        "127.0.0.1"
        if settings.host_mode == "local"
        else wait_for_tailscale_ip(
            attempts=settings.tailscale_wait_attempts,
            wait_seconds=settings.tailscale_wait_seconds,
        )
    )
    command = build_dashboard_command(
        settings=settings,
        host=host,
    )

    print("Project KATANA Dashboard Resident")
    print(
        f"Desktop: http://{host}:{settings.port}/"
    )
    print(
        f"Mobile : http://{host}:{settings.port}/mobile"
    )
    print(f"Database: {settings.database_path}")
    print(f"Host mode: {settings.host_mode}")
    print(
        "Tailscale wait: "
        f"{settings.tailscale_wait_attempts} attempts, "
        f"{settings.tailscale_wait_seconds}s interval"
    )
    print(
        "Restart policy: "
        f"max={settings.max_restarts}, "
        f"delay={settings.restart_delay_seconds}s"
    )

    if parsed.dry_run:
        print(
            subprocess.list2cmdline(command)
        )
        return 0

    return run_dashboard_supervisor(
        settings=settings,
        host=host,
    )


if __name__ == "__main__":
    raise SystemExit(run())
