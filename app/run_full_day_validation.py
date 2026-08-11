"""Project KATANA Full-Day Validation CLI。"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Sequence

from app.runtime.full_day_validation_service import (
    FullDayValidationService,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Paper Tradingの選定・監視・実行・決済・"
            "日次レポート整合性を横断検証します。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--trading-date",
        type=date.fromisoformat,
        required=True,
    )
    parser.add_argument(
        "--runtime-status",
        type=Path,
        default=Path(
            "reports/service/"
            "paper_trading_runtime_status.json"
        ),
    )
    parser.add_argument(
        "--integrity-report",
        type=Path,
        default=Path(
            "reports/service/"
            "watchlist_execution_integrity.json"
        ),
    )
    parser.add_argument(
        "--daily-report-directory",
        type=Path,
        default=Path("reports/daily"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "reports/service/"
            "full_day_validation.json"
        ),
    )
    return parser


def run(
    argv: Sequence[str] | None = None,
) -> int:
    args = build_parser().parse_args(argv)

    result = FullDayValidationService(
        database_path=args.database_path,
        runtime_status_path=args.runtime_status,
        integrity_report_path=args.integrity_report,
        daily_report_directory=(
            args.daily_report_directory
        ),
    ).validate(
        trading_date=args.trading_date
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temporary = args.output.with_suffix(
        args.output.suffix + ".tmp"
    )
    temporary.write_text(
        json.dumps(
            result.to_dict(),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(args.output)

    print("Project KATANA Full-Day Validation")
    print("=" * 48)
    print(f"trading_date={result.trading_date}")

    for check in result.checks:
        state = "PASS" if check.passed else "FAIL"
        print(
            f"[{state}] {check.label}: "
            f"{check.message}"
        )

    print("")
    print(
        "FULL-DAY VALIDATION: "
        + ("PASS" if result.passed else "FAIL")
    )
    print(
        f"failed_checks={result.failed_check_count}"
    )
    print(f"report={args.output}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(run())
