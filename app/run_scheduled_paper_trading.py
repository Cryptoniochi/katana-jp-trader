"""営業日Paper TradingスケジューラCLI。"""

from __future__ import annotations

import argparse
import signal
from pathlib import Path
from typing import Sequence

from app.runtime.scheduled_paper_trading import (
    ScheduledPaperTradingController,
)
from app.runtime.scheduled_paper_trading_models import (
    TradingScheduleSettings,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "東京市場の営業日と時刻に従って"
            "Paper Tradingを安全に制御します。"
        )
    )
    parser.add_argument(
        "--enable",
        action="store_true",
        help=(
            "明示的に指定した場合だけPaper Tradingを"
            "起動可能にします。"
        ),
    )
    parser.add_argument(
        "--status-path",
        type=Path,
        default=Path(
            "reports/service/paper_trading_schedule.json"
        ),
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=5.0,
    )
    parser.add_argument(
        "--once",
        action="store_true",
    )
    parser.add_argument(
        "--skip-readiness-check",
        action="store_true",
    )
    parser.add_argument(
        "--skip-autonomous-guard",
        action="store_true",
    )
    parser.add_argument(
        "--autonomous-guard-report-path",
        type=Path,
        default=Path(
            "reports/service/autonomous_operation_report.json"
        ),
    )
    return parser


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed, paper_arguments = (
        build_argument_parser().parse_known_args(
            arguments
        )
    )
    controller = ScheduledPaperTradingController(
        enabled=parsed.enable,
        settings=TradingScheduleSettings(),
        status_path=parsed.status_path,
        paper_arguments=paper_arguments,
        readiness_check_enabled=(
            not parsed.skip_readiness_check
        ),
        autonomous_guard_enabled=(
            not parsed.skip_autonomous_guard
        ),
        autonomous_guard_report_path=(
            parsed.autonomous_guard_report_path
        ),
    )

    def request_stop(
        _signum,
        _frame,
    ) -> None:
        controller.request_stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    if parsed.once:
        status = controller.run_once()
        print(
            f"state={status.state.value}"
        )
        print(
            f"business_day={status.business_day}"
        )
        print(
            f"enabled={status.enabled}"
        )
        print(
            f"process_id={status.process_id}"
        )
        return 0

    controller.run_forever(
        poll_interval_seconds=(
            parsed.poll_interval_seconds
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
