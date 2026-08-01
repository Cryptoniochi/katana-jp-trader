"""Morning Pre-Flight自動実行スケジューラCLI。"""

from __future__ import annotations

import argparse
import signal
from pathlib import Path
from typing import Sequence

from app.runtime.morning_preflight_scheduler import (
    MorningPreflightScheduler,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "営業日8:40にMorning Pre-Flightを"
            "LINE・Discordへ自動送信します。"
        )
    )
    parser.add_argument(
        "--enable",
        action="store_true",
    )
    parser.add_argument(
        "--status-path",
        type=Path,
        default=Path(
            "reports/service/"
            "morning_preflight_schedule.json"
        ),
    )
    parser.add_argument(
        "--marker-directory",
        type=Path,
        default=Path(
            "reports/service/morning_preflight"
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
    scheduler = MorningPreflightScheduler(
        enabled=parsed.enable,
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
