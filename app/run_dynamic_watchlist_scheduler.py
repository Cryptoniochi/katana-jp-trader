"""Dynamic Watchlist自動更新スケジューラCLI。"""

from __future__ import annotations

import argparse
import signal
from pathlib import Path
from typing import Sequence

from app.runtime.dynamic_watchlist_schedule_models import (
    DynamicWatchlistScheduleSettings,
)
from app.runtime.dynamic_watchlist_scheduler import (
    DynamicWatchlistScheduler,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "営業日8:20にDynamic Watchlistを生成し、"
            "watchlist.txtへ安全に適用します。"
        )
    )
    parser.add_argument("--enable", action="store_true")
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
        "--report-directory",
        type=Path,
        default=Path("reports/watchlist"),
    )
    parser.add_argument(
        "--status-path",
        type=Path,
        default=Path(
            "reports/service/dynamic_watchlist_schedule.json"
        ),
    )
    parser.add_argument(
        "--minimum-symbols",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--maximum-symbols",
        type=int,
        default=50,
    )
    parser.add_argument(
        "--capital-limit",
        type=float,
        default=1_000_000.0,
    )
    parser.add_argument(
        "--purchase-budget",
        type=float,
        default=950_000.0,
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=30.0,
    )
    parser.add_argument("--once", action="store_true")
    return parser


def run(arguments: Sequence[str] | None = None) -> int:
    parsed = build_argument_parser().parse_args(arguments)
    scheduler = DynamicWatchlistScheduler(
        enabled=parsed.enable,
        database_path=parsed.database_path,
        watchlist_path=parsed.watchlist_path,
        report_directory=parsed.report_directory,
        status_path=parsed.status_path,
        settings=DynamicWatchlistScheduleSettings(
            minimum_symbols=parsed.minimum_symbols,
            maximum_symbols=parsed.maximum_symbols,
            capital_limit=parsed.capital_limit,
            purchase_budget=parsed.purchase_budget,
        ),
    )

    def request_stop(_signum, _frame) -> None:
        scheduler.request_stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    if parsed.once:
        status = scheduler.run_once()
        print(f"state={status.state.value}")
        print(f"business_day={status.business_day}")
        print(f"enabled={status.enabled}")
        print(f"selected_count={status.selected_count}")
        print(f"applied={status.applied}")
        print(f"message={status.message}")
        return (
            1
            if status.state.value == "failed"
            else 0
        )

    scheduler.run_forever(
        poll_interval_seconds=parsed.poll_interval_seconds
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
