"""上場銘柄マスターCSV取込CLI。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from app.universe.listed_symbol_csv_importer import (
    ListedSymbolCsvImporter,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "上場銘柄マスターCSVを"
            "listed_symbolsへ取り込みます。"
        )
    )
    parser.add_argument(
        "csv_path",
        type=Path,
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--source-name",
        default="listed-symbols-csv",
    )
    return parser


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    symbols = ListedSymbolCsvImporter(
        database_path=parsed.database_path,
        source_name=parsed.source_name,
    ).import_file(parsed.csv_path)

    print("Project KATANA Listed Symbol Import")
    print("=" * 40)
    print(f"imported_count={len(symbols)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
