"""Dynamic Watchlist生成CLI。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from app.dynamic_watchlist.dynamic_watchlist_models import (
    DynamicWatchlistSettings,
)
from app.dynamic_watchlist.dynamic_watchlist_service import (
    DynamicWatchlistService,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "保存済み市場データを採点し、"
            "100万円で購入可能な上位銘柄を選定します。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--candidate-universe-path",
        type=Path,
        default=Path(
            "data/universe_candidates.txt"
        ),
    )
    parser.add_argument(
        "--ignore-candidate-universe",
        action="store_true",
    )
    parser.add_argument(
        "--require-candidate-universe",
        action="store_true",
    )
    parser.add_argument(
        "--watchlist-path",
        type=Path,
        default=Path("watchlist.txt"),
    )
    parser.add_argument(
        "--report-directory",
        type=Path,
        default=Path("reports/watchlist"),
    )
    parser.add_argument(
        "--capital-limit",
        type=float,
        default=1_000_000.0,
    )
    parser.add_argument(
        "--purchase-budget",
        type=float,
        default=950_000.0,
    )
    parser.add_argument(
        "--trading-unit",
        type=int,
        default=100,
    )
    parser.add_argument(
        "--maximum-symbols",
        type=int,
        default=50,
    )
    parser.add_argument(
        "--minimum-symbols",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--minimum-history-days",
        type=int,
        default=20,
    )
    parser.add_argument(
        "--fallback-minimum-history-days",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--fallback-minimum-average-turnover",
        type=float,
        default=5_000_000.0,
    )
    parser.add_argument(
        "--fallback-minimum-average-volume",
        type=float,
        default=5_000.0,
    )
    parser.add_argument(
        "--fallback-maximum-data-age-days",
        type=int,
        default=45,
    )
    parser.add_argument(
        "--minimum-average-turnover",
        type=float,
        default=50_000_000.0,
    )
    parser.add_argument(
        "--minimum-average-volume",
        type=float,
        default=50_000.0,
    )
    parser.add_argument(
        "--maximum-data-age-days",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--disable-learning-feedback",
        action="store_true",
    )
    parser.add_argument(
        "--learning-total-score-weight",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--learning-strategy-score-weight",
        type=float,
        default=0.25,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "検証成功時にwatchlist.txtを更新します。"
            "未指定時はDry Runです。"
        ),
    )
    return parser


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    settings = DynamicWatchlistSettings(
        capital_limit=parsed.capital_limit,
        purchase_budget=parsed.purchase_budget,
        trading_unit=parsed.trading_unit,
        maximum_symbols=parsed.maximum_symbols,
        minimum_symbols=parsed.minimum_symbols,
        minimum_history_days=parsed.minimum_history_days,
        fallback_minimum_history_days=(
            parsed.fallback_minimum_history_days
        ),
        fallback_minimum_average_turnover=(
            parsed.fallback_minimum_average_turnover
        ),
        fallback_minimum_average_volume=(
            parsed.fallback_minimum_average_volume
        ),
        fallback_maximum_data_age_days=(
            parsed.fallback_maximum_data_age_days
        ),
        minimum_average_turnover=(
            parsed.minimum_average_turnover
        ),
        minimum_average_volume=(
            parsed.minimum_average_volume
        ),
        maximum_data_age_days=(
            parsed.maximum_data_age_days
        ),
        learning_feedback_enabled=(
            not parsed.disable_learning_feedback
        ),
        learning_total_score_weight=(
            parsed.learning_total_score_weight
        ),
        learning_strategy_score_weight=(
            parsed.learning_strategy_score_weight
        ),
    )
    result = DynamicWatchlistService(
        database_path=parsed.database_path,
        watchlist_path=parsed.watchlist_path,
        report_directory=parsed.report_directory,
        settings=settings,
        candidate_universe_path=(
            None
            if parsed.ignore_candidate_universe
            else parsed.candidate_universe_path
        ),
        require_candidate_universe=(
            parsed.require_candidate_universe
        ),
    ).generate(
        apply=parsed.apply
    )

    print("Project KATANA Dynamic Watchlist")
    print("=" * 42)
    print(f"evaluated_count={result.evaluated_count}")
    print(f"eligible_count={result.eligible_count}")
    print(f"selected_count={len(result.selected)}")
    print(f"applied={result.applied}")
    print(f"message={result.message}")
    print()
    print(
        "Rank  Code   Tier  Strategy       Tech   Hist   Total   "
        "Price      100-share amount"
    )

    for rank, candidate in enumerate(
        result.selected,
        start=1,
    ):
        print(
            f"{rank:>4}  {candidate.code:<5} "
            f"{candidate.rating_tier:<5} "
            f"{candidate.preferred_strategy:<14} "
            f"{candidate.technical_score:>6.2f} "
            f"{candidate.historical_score:>6.2f} "
            f"{candidate.total_score:>7.2f} "
            f"{candidate.latest_price:>10,.1f} "
            f"{candidate.purchase_amount:>17,.0f}"
        )

    if parsed.apply and not result.applied:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
