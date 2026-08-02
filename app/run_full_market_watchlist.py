"""全市場一次選定からDynamic Watchlistまで連続実行する。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.dynamic_watchlist.dynamic_watchlist_models import (
    DynamicWatchlistSettings,
)
from app.dynamic_watchlist.dynamic_watchlist_service import (
    DynamicWatchlistService,
)
from app.universe.universe_models import (
    UniverseScreeningSettings,
)
from app.universe.universe_primary_screener import (
    UniversePrimaryScreener,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--candidate-output",
        type=Path,
        default=Path("data/universe_candidates.txt"),
    )
    parser.add_argument(
        "--watchlist-path",
        type=Path,
        default=Path("watchlist.txt"),
    )
    parser.add_argument(
        "--universe-report",
        type=Path,
        default=Path(
            "reports/universe/"
            "primary_screening_latest.json"
        ),
    )
    parser.add_argument(
        "--watchlist-report-directory",
        type=Path,
        default=Path("reports/watchlist"),
    )
    parser.add_argument(
        "--primary-maximum-symbols",
        type=int,
        default=300,
    )
    parser.add_argument(
        "--final-maximum-symbols",
        type=int,
        default=50,
    )
    parser.add_argument(
        "--minimum-symbols",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--maximum-purchase-amount",
        type=float,
        default=950_000.0,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
    )
    return parser


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    args = build_argument_parser().parse_args(
        arguments
    )

    universe_report = UniversePrimaryScreener(
        database_path=args.database_path,
        settings=UniverseScreeningSettings(
            maximum_symbols=(
                args.primary_maximum_symbols
            ),
            maximum_purchase_amount=(
                args.maximum_purchase_amount
            ),
        ),
    ).screen()

    args.candidate_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.candidate_output.write_text(
        "\n".join(
            item.code
            for item in universe_report.selected
        )
        + ("\n" if universe_report.selected else ""),
        encoding="utf-8",
    )

    args.universe_report.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.universe_report.write_text(
        json.dumps(
            universe_report.to_dict(),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    watchlist_result = DynamicWatchlistService(
        database_path=args.database_path,
        watchlist_path=args.watchlist_path,
        report_directory=(
            args.watchlist_report_directory
        ),
        settings=DynamicWatchlistSettings(
            maximum_symbols=(
                args.final_maximum_symbols
            ),
            minimum_symbols=args.minimum_symbols,
            purchase_budget=(
                args.maximum_purchase_amount
            ),
        ),
        candidate_universe_path=(
            args.candidate_output
        ),
        require_candidate_universe=True,
    ).generate(apply=args.apply)

    print("Project KATANA Full Market Pipeline")
    print("=" * 44)
    print(
        f"universe_count={universe_report.universe_count}"
    )
    print(
        f"primary_selected={universe_report.selected_count}"
    )
    print(
        f"dynamic_evaluated={watchlist_result.evaluated_count}"
    )
    print(
        f"dynamic_selected={len(watchlist_result.selected)}"
    )
    print(f"applied={watchlist_result.applied}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
