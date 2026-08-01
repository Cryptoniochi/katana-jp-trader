"""Performance Breakdown CLI。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.analytics.performance_breakdown_service import (
    PerformanceBreakdownAnalyzer,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Trade Journalを曜日・時間帯・銘柄・"
            "決済理由別に分析します。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--symbol-limit",
        type=int,
        default=20,
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path(
            "reports/performance_breakdown.json"
        ),
    )
    return parser


def run(
    arguments: list[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    payload = PerformanceBreakdownAnalyzer(
        parsed.database_path,
        symbol_limit=parsed.symbol_limit,
    ).analyze()

    parsed.output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    parsed.output_path.write_text(
        json.dumps(
            payload.to_dict(),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    print("Performance breakdown completed.")
    print(
        f"weekday_rows={len(payload.weekday)}"
    )
    print(
        f"entry_hour_rows={len(payload.entry_hour)}"
    )
    print(
        f"symbol_rows={len(payload.symbol)}"
    )
    print(
        f"exit_reason_rows={len(payload.exit_reason)}"
    )
    print(parsed.output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
