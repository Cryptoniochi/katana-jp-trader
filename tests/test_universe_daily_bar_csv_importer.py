"""UniverseDailyBarCsvImporterのテスト。"""

import sqlite3
from pathlib import Path

from app.universe.universe_daily_bar_csv_importer import (
    UniverseDailyBarCsvImporter,
)


def test_imports_daily_bars_and_is_idempotent(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    csv_path = tmp_path / "daily.csv"
    csv_path.write_text(
        "\n".join(
            [
                "code,date,open,high,low,close,volume",
                "7203,2026-08-03,3000,3050,2980,3030,1000000",
                "8306,2026-08-03,1500,1530,1490,1520,2000000",
            ]
        ),
        encoding="utf-8",
    )

    importer = UniverseDailyBarCsvImporter(
        database_path=database,
        source_name="test-source",
    )

    first = importer.import_file(csv_path)
    second = importer.import_file(csv_path)

    assert first.imported_row_count == 2
    assert second.imported_row_count == 2
    assert first.symbol_count == 2

    with sqlite3.connect(database) as connection:
        count = connection.execute(
            """
            SELECT COUNT(*)
            FROM market_bars
            WHERE interval_minutes = 1440
              AND data_source = 'test-source'
            """
        ).fetchone()[0]

    assert count == 2


def test_supports_japanese_headers(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    csv_path = tmp_path / "daily.csv"
    csv_path.write_text(
        "\n".join(
            [
                "銘柄コード,日付,始値,高値,安値,終値,出来高",
                "7203,20260803,3000,3050,2980,3030,1000000",
            ]
        ),
        encoding="utf-8",
    )

    result = UniverseDailyBarCsvImporter(
        database_path=database
    ).import_file(csv_path)

    assert result.imported_row_count == 1
    assert result.latest_date.isoformat() == "2026-08-03"


def test_can_skip_invalid_rows(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    csv_path = tmp_path / "daily.csv"
    csv_path.write_text(
        "\n".join(
            [
                "code,date,open,high,low,close,volume",
                "7203,2026-08-03,3000,3050,2980,3030,1000000",
                "bad,not-a-date,x,x,x,x,x",
            ]
        ),
        encoding="utf-8",
    )

    result = UniverseDailyBarCsvImporter(
        database_path=database
    ).import_file(
        csv_path,
        skip_invalid_rows=True,
    )

    assert result.imported_row_count == 1
    assert result.skipped_row_count == 1
