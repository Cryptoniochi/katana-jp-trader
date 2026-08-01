"""Project KATANA自律運転検証CLI。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.runtime.autonomous_operation_validator import (
    AutonomousOperationValidator,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "次営業日の自律運転開始可否を確認します。"
        )
    )
    parser.add_argument(
        "--service-status-path",
        type=Path,
        default=Path(
            "reports/service/katana_service_status.json"
        ),
    )
    parser.add_argument(
        "--paper-schedule-status-path",
        type=Path,
        default=Path(
            "reports/service/paper_trading_schedule.json"
        ),
    )
    parser.add_argument(
        "--daily-report-schedule-status-path",
        type=Path,
        default=Path(
            "reports/service/daily_report_schedule.json"
        ),
    )
    parser.add_argument(
        "--watchlist-path",
        type=Path,
        default=Path("watchlist.txt"),
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path(
            "reports/service/"
            "autonomous_operation_report.json"
        ),
    )
    return parser


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    report = AutonomousOperationValidator(
        service_status_path=(
            parsed.service_status_path
        ),
        paper_schedule_status_path=(
            parsed.paper_schedule_status_path
        ),
        daily_report_schedule_status_path=(
            parsed.daily_report_schedule_status_path
        ),
        watchlist_path=parsed.watchlist_path,
        database_path=parsed.database_path,
    ).evaluate()

    parsed.output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    parsed.output_path.write_text(
        json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "Project KATANA Autonomous Operation Validation"
    )
    print("=" * 52)

    for check in report.checks:
        print(
            f"[{check.level.value.upper():7}] "
            f"{check.label}: {check.message}"
        )

    print()
    print(f"Overall: {report.overall_state.upper()}")
    print(
        "Ready for next business day: "
        f"{report.ready_for_next_business_day}"
    )
    print(parsed.output_path)

    return (
        0
        if report.ready_for_next_business_day
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(run())
