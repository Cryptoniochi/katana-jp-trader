"""Strategy Learningを実行するCLI。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.learning.strategy_learning_service import (
    StrategyLearningService,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Trade Journalから銘柄×戦略の"
            "学習結果を生成します。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--minimum-trade-count",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--full-confidence-trade-count",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path(
            "reports/learning/"
            "strategy_learning_latest.json"
        ),
    )
    return parser


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    report = StrategyLearningService(
        parsed.database_path,
        minimum_trade_count=(
            parsed.minimum_trade_count
        ),
        full_confidence_trade_count=(
            parsed.full_confidence_trade_count
        ),
    ).analyze_and_persist()

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

    print("Project KATANA Strategy Learning")
    print("=" * 40)
    print(f"records={report.record_count}")
    print(
        "recommendations="
        f"{report.recommendation_count}"
    )
    print(
        "minimum_trade_count="
        f"{report.minimum_trade_count}"
    )
    print()
    print("Code   Preferred Strategy   Eligible")

    for item in report.recommendations:
        print(
            f"{item.code:<6} "
            f"{(item.preferred_strategy or 'pending'):<20} "
            f"{item.eligible_strategy_count:>8}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
