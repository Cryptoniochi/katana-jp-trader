"""全市場Daily History Audit CLI。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

from app.runtime.universe_daily_history_audit_service import (
    UniverseDailyHistoryAuditService,
)


TOKYO = ZoneInfo("Asia/Tokyo")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "全市場の日足蓄積件数・欠損・"
            "履歴成熟度を監査します。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--trading-date",
        type=lambda value: datetime.fromisoformat(
            value
        ).date(),
        default=None,
    )
    parser.add_argument(
        "--minimum-effective-coverage-ratio",
        type=float,
        default=0.99,
    )
    parser.add_argument(
        "--terminal-skip-path",
        type=Path,
        default=Path(
            "reports/universe/"
            "bootstrap_unavailable.json"
        ),
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path(
            "reports/universe/"
            "daily_history_audit_latest.json"
        ),
    )
    return parser


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    trading_date = (
        parsed.trading_date
        if parsed.trading_date is not None
        else datetime.now(TOKYO).date()
    )

    result = UniverseDailyHistoryAuditService(
        database_path=parsed.database_path,
        minimum_effective_coverage_ratio=(
            parsed.minimum_effective_coverage_ratio
        ),
        terminal_skip_path=(
            parsed.terminal_skip_path
        ),
    ).audit(
        trading_date=trading_date
    )

    parsed.report_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temporary = parsed.report_path.with_suffix(
        parsed.report_path.suffix + ".tmp"
    )
    temporary.write_text(
        json.dumps(
            result.to_dict(),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(
        parsed.report_path
    )

    print(
        "Project KATANA Universe Daily History Audit"
    )
    print("=" * 56)
    print(
        f"trading_date={result.trading_date}"
    )
    print(
        "active_universe="
        f"{result.active_universe_count}"
    )
    print(
        f"collected={result.collected_count}"
    )
    print(
        f"missing={result.missing_count}"
    )
    print(
        "terminal_skipped="
        f"{result.terminal_skipped_count}"
    )
    print(
        "unexplained_missing="
        f"{result.unexplained_missing_count}"
    )
    print(
        "collection_ratio="
        f"{result.collection_ratio:.4f}"
    )
    print(
        "effective_coverage_ratio="
        f"{result.effective_coverage_ratio:.4f}"
    )
    print(
        f"fallback={result.fallback_count}"
    )
    print(
        f"developing={result.developing_count}"
    )
    print(
        f"strict={result.strict_count}"
    )
    print(
        f"completed={result.completed}"
    )

    if result.unexplained_missing_codes:
        print(
            "Unexplained missing codes "
            "(first 20)"
        )
        for code in (
            result.unexplained_missing_codes[:20]
        ):
            print(f"  {code}")

    return 0 if result.completed else 1


if __name__ == "__main__":
    raise SystemExit(run())
