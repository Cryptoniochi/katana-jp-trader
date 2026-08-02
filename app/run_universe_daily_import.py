"""全市場日足CSV取込CLI。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.universe.universe_daily_bar_csv_importer import (
    UniverseDailyBarCsvImporter,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "約4,000銘柄の日足CSVを"
            "market_barsへ取り込みます。"
        )
    )
    parser.add_argument("csv_path", type=Path)
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--source-name",
        default="universe-daily-csv",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10_000,
    )
    parser.add_argument(
        "--skip-invalid-rows",
        action="store_true",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path(
            "reports/universe/"
            "daily_import_latest.json"
        ),
    )
    return parser


def run(arguments: Sequence[str] | None = None) -> int:
    args = build_argument_parser().parse_args(arguments)

    result = UniverseDailyBarCsvImporter(
        database_path=args.database_path,
        source_name=args.source_name,
        batch_size=args.batch_size,
    ).import_file(
        args.csv_path,
        skip_invalid_rows=args.skip_invalid_rows,
    )

    args.report_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.report_path.write_text(
        json.dumps(
            result.to_dict(),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("Project KATANA Universe Daily Import")
    print("=" * 40)
    print(f"input_rows={result.input_row_count}")
    print(f"imported_rows={result.imported_row_count}")
    print(f"skipped_rows={result.skipped_row_count}")
    print(f"symbols={result.symbol_count}")
    print(f"earliest_date={result.earliest_date}")
    print(f"latest_date={result.latest_date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
