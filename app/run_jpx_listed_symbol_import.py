"""JPX公式上場銘柄一覧をProject KATANAへ取り込むCLI。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.universe.jpx_listed_symbol_importer import (
    DEFAULT_JPX_PAGE_URL,
    JpxListedSymbolImporter,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "JPX公式の東証上場銘柄一覧を取得し、"
            "Prime/Standard/Growthの内国普通株を"
            "listed_symbolsへ保存します。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "ダウンロード済みJPX .xls/.xlsx/.csv。"
            "省略時は公式ページから最新版を自動取得します。"
        ),
    )
    parser.add_argument(
        "--page-url",
        default=DEFAULT_JPX_PAGE_URL,
    )
    parser.add_argument(
        "--download-directory",
        type=Path,
        default=Path("data/reference/jpx"),
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path(
            "reports/universe/"
            "listed_symbols_latest.json"
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
    )
    return parser


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(arguments)

    importer = JpxListedSymbolImporter(
        database_path=parsed.database_path,
        timeout_seconds=parsed.timeout_seconds,
    )

    if parsed.input is None:
        result = importer.import_latest(
            page_url=parsed.page_url,
            destination_directory=(
                parsed.download_directory
            ),
        )
    else:
        result = importer.import_file(
            parsed.input
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

    print("Project KATANA JPX Listed Symbol Import")
    print("=" * 48)
    print(f"raw_rows={result.raw_row_count}")
    print(f"imported={result.imported_count}")
    print(f"skipped={result.skipped_count}")
    print(f"Prime={result.prime_count}")
    print(f"Standard={result.standard_count}")
    print(f"Growth={result.growth_count}")
    print(f"source={result.source_path}")

    return 0 if result.imported_count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
