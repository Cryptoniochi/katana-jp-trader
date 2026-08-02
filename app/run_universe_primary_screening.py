"""全市場一次スクリーニングCLI。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.universe.universe_models import (
    UniverseScreeningSettings,
)
from app.universe.universe_primary_screener import (
    UniversePrimaryScreener,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "全市場ユニバースを最大300銘柄へ"
            "一次スクリーニングします。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--maximum-symbols",
        type=int,
        default=300,
    )
    parser.add_argument(
        "--maximum-purchase-amount",
        type=float,
        default=950_000.0,
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path(
            "reports/universe/"
            "primary_screening_latest.json"
        ),
    )
    parser.add_argument(
        "--candidate-output",
        type=Path,
        default=Path(
            "data/universe_candidates.txt"
        ),
    )
    return parser


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    report = UniversePrimaryScreener(
        database_path=parsed.database_path,
        settings=UniverseScreeningSettings(
            maximum_symbols=(
                parsed.maximum_symbols
            ),
            maximum_purchase_amount=(
                parsed.maximum_purchase_amount
            ),
        ),
    ).screen()

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

    parsed.candidate_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    parsed.candidate_output.write_text(
        "\n".join(
            item.code
            for item in report.selected
        )
        + (
            "\n"
            if report.selected
            else ""
        ),
        encoding="utf-8",
    )

    print("Project KATANA Universe Screening")
    print("=" * 40)
    print(
        f"universe_count={report.universe_count}"
    )
    print(
        f"evaluated_count={report.evaluated_count}"
    )
    print(
        f"eligible_count={report.eligible_count}"
    )
    print(
        f"selected_count={report.selected_count}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
