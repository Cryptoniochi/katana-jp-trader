"""Project KATANA日次取引レポート生成CLI。"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Sequence

from app.runtime.daily_report_service import (
    DailyReportService,
    SQLiteDailyTradeRepository,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Project KATANAの日次取引レポートを生成します。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--report-date",
        type=date.fromisoformat,
        default=date.today(),
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--error-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--recovery-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--note",
        action="append",
        default=[],
    )
    return parser


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    output_path = (
        parsed.output_path
        if parsed.output_path is not None
        else Path(
            "reports/daily"
        )
        / f"{parsed.report_date.isoformat()}.json"
    )
    report = DailyReportService(
        SQLiteDailyTradeRepository(
            parsed.database_path
        )
    ).generate_and_save(
        report_date=parsed.report_date,
        output_path=output_path,
        error_count=parsed.error_count,
        recovery_count=parsed.recovery_count,
        notes=parsed.note,
    )

    print("Daily trading report generated.")
    print(f"date={report.report_date}")
    print(f"status={report.status.value}")
    print(
        "net_profit_loss="
        f"{report.summary.net_profit_loss}"
    )
    print(
        f"trade_count={report.summary.trade_count}"
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
