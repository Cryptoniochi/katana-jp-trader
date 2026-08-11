"""Watchlist-to-Execution Integrity Audit CLI。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

from app.runtime.watchlist_execution_integrity_service import (
    WatchlistExecutionIntegrityService,
)


TOKYO = ZoneInfo("Asia/Tokyo")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dynamic WatchlistからPaper Trading約定までの"
            "銘柄整合性を監査します。"
        )
    )
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
        "--explainability-path",
        type=Path,
        default=Path(
            "reports/watchlist/explainability/latest.json"
        ),
    )
    parser.add_argument(
        "--trace-path",
        type=Path,
        default=Path(
            "logs/risk/paper_trading_trace.jsonl"
        ),
    )
    parser.add_argument(
        "--trading-date",
        type=lambda value: datetime.fromisoformat(
            value
        ).date(),
        default=None,
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path(
            "reports/service/"
            "watchlist_execution_integrity.json"
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

    result = WatchlistExecutionIntegrityService(
        database_path=parsed.database_path,
        watchlist_path=parsed.watchlist_path,
        explainability_path=(
            parsed.explainability_path
        ),
        trace_path=parsed.trace_path,
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
    temporary.replace(parsed.report_path)

    print(
        "Project KATANA Watchlist-to-Execution Integrity"
    )
    print("=" * 58)
    print(
        f"trading_date={result.trading_date}"
    )
    print(
        f"selected={result.selected_count}"
    )
    print(
        f"loaded={result.loaded_count}"
    )
    print(
        f"monitored={result.monitored_count}"
    )
    print(
        f"signals={result.signal_count}"
    )
    print(
        f"executions={result.execution_count}"
    )
    print(
        f"trace_available={result.trace_available}"
    )
    print(
        f"integrity={'PASS' if result.integrity_ok else 'FAIL'}"
    )

    for item in result.symbol_audits:
        print(
            f"{item.code} "
            f"selected={item.selected} "
            f"loaded={item.loaded} "
            f"monitored={item.monitored} "
            f"signals={item.signal_count} "
            f"executions={item.execution_count} "
            f"status={item.status}"
        )

    if result.selected_not_loaded_codes:
        print(
            "Selected but not loaded: "
            + ",".join(
                result.selected_not_loaded_codes
            )
        )
    if result.loaded_not_monitored_codes:
        print(
            "Loaded but not monitored: "
            + ",".join(
                result.loaded_not_monitored_codes
            )
        )
    if result.monitored_not_loaded_codes:
        print(
            "Monitored but not loaded: "
            + ",".join(
                result.monitored_not_loaded_codes
            )
        )
    if result.orphan_signal_codes:
        print(
            "Orphan signals: "
            + ",".join(
                result.orphan_signal_codes
            )
        )
    if result.orphan_execution_codes:
        print(
            "Orphan executions: "
            + ",".join(
                result.orphan_execution_codes
            )
        )

    return 0 if result.integrity_ok else 1


if __name__ == "__main__":
    raise SystemExit(run())
