"""Dynamic Watchlist戦略ルーティング確認CLI。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.dynamic_watchlist.strategy_routing_repository import (
    DynamicWatchlistStrategyRoutingRepository,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dynamic Watchlist latest.jsonから"
            "銘柄別推奨戦略ルートを生成します。"
        )
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path(
            "reports/watchlist/latest.json"
        ),
    )
    parser.add_argument(
        "--minimum-rating-tier",
        choices=("A+", "A", "B", "C"),
        default="C",
    )
    parser.add_argument(
        "--minimum-total-score",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path(
            "reports/watchlist/"
            "strategy_routing_latest.json"
        ),
    )
    return parser


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    snapshot = (
        DynamicWatchlistStrategyRoutingRepository(
            report_path=parsed.report_path,
            minimum_rating_tier=(
                parsed.minimum_rating_tier
            ),
            minimum_total_score=(
                parsed.minimum_total_score
            ),
        ).load()
    )

    parsed.output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    parsed.output_path.write_text(
        json.dumps(
            snapshot.to_dict(),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("Project KATANA Strategy Routing")
    print("=" * 40)
    print(f"route_count={snapshot.route_count}")
    print(
        "fallback_strategies="
        + ",".join(
            snapshot.fallback_strategy_names
        )
    )
    print()
    print("Code   Strategy        Tier   Total   Strategy")

    for route in snapshot.routes:
        print(
            f"{route.code:<6} "
            f"{route.strategy_name:<15} "
            f"{route.rating_tier:<6} "
            f"{route.total_score:>6.2f} "
            f"{route.strategy_score:>8.2f}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
