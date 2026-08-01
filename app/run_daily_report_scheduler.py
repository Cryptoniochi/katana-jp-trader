"""Daily Report自動生成・通知スケジューラCLI。"""

from __future__ import annotations

import argparse
import signal
from pathlib import Path
from typing import Sequence

from app.runtime.daily_report_scheduler import (
    DailyReportScheduler,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "営業日15:40にDaily Reportを生成し、"
            "LINE・Discordへ通知します。"
        )
    )
    parser.add_argument(
        "--enable",
        action="store_true",
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--report-directory",
        type=Path,
        default=Path("reports/daily"),
    )
    parser.add_argument(
        "--status-path",
        type=Path,
        default=Path(
            "reports/service/daily_report_schedule.json"
        ),
    )
    parser.add_argument(
        "--marker-directory",
        type=Path,
        default=Path(
            "reports/daily/notifications"
        ),
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=30.0,
    )
    parser.add_argument(
        "--once",
        action="store_true",
    )
    return parser


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    scheduler = DailyReportScheduler(
        enabled=parsed.enable,
        database_path=parsed.database_path,
        report_directory=parsed.report_directory,
        status_path=parsed.status_path,
        marker_directory=parsed.marker_directory,
    )

    def request_stop(
        _signum,
        _frame,
    ) -> None:
        scheduler.request_stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    if parsed.once:
        status = scheduler.run_once()
        print(f"state={status.state.value}")
        print(f"business_day={status.business_day}")
        print(f"enabled={status.enabled}")
        print(f"message={status.message}")
        return (
            1
            if status.state.value == "failed"
            else 0
        )

    scheduler.run_forever(
        poll_interval_seconds=(
            parsed.poll_interval_seconds
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
