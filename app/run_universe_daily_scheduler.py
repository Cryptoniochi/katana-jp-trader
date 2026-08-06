"""Universe Daily Scheduler CLI。"""

from __future__ import annotations

import argparse
import signal
from pathlib import Path

from app.runtime.universe_daily_scheduler import (
    UniverseDailyScheduler,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--enable",
        action="store_true",
    )
    parser.add_argument(
        "--once",
        action="store_true",
    )
    return parser


def run(arguments=None) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
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
        return (
            0
            if status.state.value
            not in {"failed"}
            else 1
        )

    scheduler.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
