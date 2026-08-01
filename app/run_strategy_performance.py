"""戦略別Performance Analyzer CLI。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from app.analytics.strategy_performance_service import (
    StrategyPerformanceAnalyzer,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Trade Journalから戦略成績を集計します。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--start-at",
        type=datetime.fromisoformat,
        default=None,
    )
    parser.add_argument(
        "--end-at",
        type=datetime.fromisoformat,
        default=None,
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path(
            "reports/strategy_performance.json"
        ),
    )
    return parser


def run(
    arguments: list[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    payload = StrategyPerformanceAnalyzer(
        parsed.database_path
    ).analyze(
        start_at=parsed.start_at,
        end_at=parsed.end_at,
    )

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

    print("Strategy performance analysis completed.")
    print(
        f"strategy_count={len(payload.rankings)}"
    )

    for index, performance in enumerate(
        payload.rankings,
        start=1,
    ):
        print(
            f"{index}. {performance.strategy_name} "
            f"score={performance.score:.2f} "
            f"trades={performance.trade_count} "
            f"net_pl={performance.net_profit_loss:.2f}"
        )

    print(parsed.output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
