"""Project KATANA Service Manager CLI。"""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from app.run_dashboard_resident import (
    wait_for_tailscale_ip,
)
from app.runtime.kabu_station_readiness_probe import (
    probe_kabu_station_readiness,
)
from app.runtime.katana_service_manager import (
    DEFAULT_STATUS_PATH,
    KatanaServiceManager,
    ManagedProcessDefinition,
    build_dashboard_command,
    build_paper_trading_command,
    build_scheduled_paper_trading_command,
    build_daily_report_scheduler_command,
    build_dynamic_watchlist_scheduler_command,
    build_morning_preflight_scheduler_command,
)
from app.runtime.katana_service_models import (
    ManagedComponentName,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Project KATANAのDashboardと任意のPaper Tradingを"
            "一元管理します。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--watchlist-path",
        type=Path,
        default=Path("watchlist.txt"),
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=8000,
    )
    parser.add_argument(
        "--status-path",
        type=Path,
        default=DEFAULT_STATUS_PATH,
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=5.0,
    )
    parser.add_argument(
        "--tailscale-wait-attempts",
        type=int,
        default=60,
    )
    parser.add_argument(
        "--tailscale-wait-seconds",
        type=float,
        default=5.0,
    )
    parser.add_argument(
        "--enable-dynamic-watchlist-schedule",
        action="store_true",
        help=(
            "営業日8:20のDynamic Watchlist自動更新を"
            "有効化します。"
        ),
    )
    parser.add_argument(
        "--enable-morning-preflight-schedule",
        action="store_true",
        help=(
            "営業日8:40のMorning Pre-Flight自動通知を"
            "有効化します。"
        ),
    )
    parser.add_argument(
        "--enable-daily-report-schedule",
        action="store_true",
        help=(
            "営業日15:40の日次レポート生成・通知を"
            "有効化します。"
        ),
    )
    parser.add_argument(
        "--enable-paper-trading-schedule",
        action="store_true",
        help=(
            "営業日スケジューラを有効化します。"
            "Paper Tradingは8:45～15:35だけ起動可能です。"
        ),
    )
    parser.add_argument(
        "--enable-paper-trading",
        action="store_true",
        help=(
            "Paper Tradingを明示的に有効化します。"
            "未指定時はDashboardだけを管理します。"
        ),
    )
    parser.add_argument(
        "--strategy",
        action="append",
        choices=(
            "orb",
            "pullback",
            "high-breakout",
        ),
        default=[],
    )
    parser.add_argument(
        "--skip-readiness-check",
        action="store_true",
    )
    parser.add_argument(
        "--readiness-interval-seconds",
        type=float,
        default=60.0,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )
    return parser


def run_kabu_station_readiness_check() -> int:
    """既存のProduction Readiness Checkを実行する。"""

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.run_paper_trading",
            "--check",
        ],
        check=False,
        cwd=Path.cwd(),
    )
    return int(completed.returncode)


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    strategies = tuple(
        parsed.strategy
        or (
            "orb",
            "pullback",
            "high-breakout",
        )
    )

    tailscale_ip = wait_for_tailscale_ip(
        attempts=parsed.tailscale_wait_attempts,
        wait_seconds=parsed.tailscale_wait_seconds,
    )

    definitions = [
        ManagedProcessDefinition(
            name=ManagedComponentName.DASHBOARD,
            command=build_dashboard_command(
                database_path=parsed.database_path,
                host=tailscale_ip,
                port=parsed.dashboard_port,
                service_status_path=parsed.status_path,
            ),
            enabled=True,
            restart_on_failure=True,
            restart_delay_seconds=10.0,
            maximum_restarts=100,
        ),
        ManagedProcessDefinition(
            name=ManagedComponentName.DYNAMIC_WATCHLIST_SCHEDULER,
            command=build_dynamic_watchlist_scheduler_command(
                database_path=parsed.database_path,
                watchlist_path=parsed.watchlist_path,
                enabled=(
                    parsed.enable_dynamic_watchlist_schedule
                ),
            ),
            enabled=True,
            restart_on_failure=True,
            restart_delay_seconds=30.0,
            maximum_restarts=20,
        ),
        ManagedProcessDefinition(
            name=ManagedComponentName.MORNING_PREFLIGHT_SCHEDULER,
            command=build_morning_preflight_scheduler_command(
                enabled=(
                    parsed.enable_morning_preflight_schedule
                ),
            ),
            enabled=True,
            restart_on_failure=True,
            restart_delay_seconds=30.0,
            maximum_restarts=20,
        ),
        ManagedProcessDefinition(
            name=ManagedComponentName.DAILY_REPORT_SCHEDULER,
            command=build_daily_report_scheduler_command(
                database_path=parsed.database_path,
                enabled=(
                    parsed.enable_daily_report_schedule
                ),
            ),
            enabled=True,
            restart_on_failure=True,
            restart_delay_seconds=30.0,
            maximum_restarts=20,
        ),
        ManagedProcessDefinition(
            name=ManagedComponentName.PAPER_TRADING_SCHEDULER,
            command=build_scheduled_paper_trading_command(
                database_path=parsed.database_path,
                watchlist_path=parsed.watchlist_path,
                strategies=strategies,
                enabled=(
                    parsed.enable_paper_trading_schedule
                ),
            ),
            enabled=True,
            restart_on_failure=True,
            restart_delay_seconds=30.0,
            maximum_restarts=20,
        ),
        # Direct Paper Trading is retained for diagnostics only.
        # Normal automated operation uses PAPER_TRADING_SCHEDULER.
        ManagedProcessDefinition(
            name=ManagedComponentName.PAPER_TRADING,
            command=build_paper_trading_command(
                database_path=parsed.database_path,
                watchlist_path=parsed.watchlist_path,
                strategies=strategies,
            ),
            enabled=parsed.enable_paper_trading,
            restart_on_failure=False,
            restart_delay_seconds=30.0,
            maximum_restarts=0,
        ),
    ]

    manager = KatanaServiceManager(
        definitions=definitions,
        status_path=parsed.status_path,
        readiness_probe=(
            None
            if parsed.skip_readiness_check
            else probe_kabu_station_readiness
        ),
        readiness_interval_seconds=(
            parsed.readiness_interval_seconds
        ),
    )

    manager.set_kabu_station_readiness(
        "not_checked"
    )

    if parsed.dry_run:
        print(f"Tailscale IP: {tailscale_ip}")

        for definition in definitions:
            print(
                f"{definition.name.value}: "
                f"enabled={definition.enabled}"
            )
            print(
                subprocess.list2cmdline(
                    list(definition.command)
                )
            )

        return 0

    def request_stop(
        _signum,
        _frame,
    ) -> None:
        manager.request_stop()

    signal.signal(
        signal.SIGINT,
        request_stop,
    )
    signal.signal(
        signal.SIGTERM,
        request_stop,
    )

    print("Project KATANA Service Manager")
    print("Market data: kabuステーション API")
    print(f"Tailscale: {tailscale_ip}")
    print(
        "Paper Trading: "
        f"{'enabled' if parsed.enable_paper_trading else 'disabled'}"
    )
    print(f"Status: {parsed.status_path}")
    print("Stop: Ctrl+C")

    manager.run_forever(
        poll_interval_seconds=(
            parsed.poll_interval_seconds
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
