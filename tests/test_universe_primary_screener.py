"""UniversePrimaryScreenerのテスト。"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.universe.listed_symbol_csv_importer import (
    ListedSymbolCsvImporter,
)
from app.universe.universe_models import (
    UniverseScreeningSettings,
)
from app.universe.universe_primary_screener import (
    UniversePrimaryScreener,
)


NOW = datetime(
    2026,
    8,
    3,
    tzinfo=timezone.utc,
)


def prepare_database(
    tmp_path: Path,
) -> Path:
    database = tmp_path / "katana.db"
    csv_path = tmp_path / "symbols.csv"
    csv_path.write_text(
        "\n".join(
            [
                "code,name,market,security_type,trading_unit",
                "7203,Toyota,Prime,common_stock,100",
                "9984,SoftBank,Prime,common_stock,100",
            ]
        ),
        encoding="utf-8",
    )

    ListedSymbolCsvImporter(
        database_path=database,
        now_provider=lambda: NOW,
    ).import_file(csv_path)

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE market_bars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                traded_at TEXT NOT NULL,
                interval_minutes INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER NOT NULL,
                data_source TEXT NOT NULL
            )
            """
        )

        connection.executemany(
            """
            INSERT INTO market_bars (
                code,
                traded_at,
                interval_minutes,
                open,
                high,
                low,
                close,
                volume,
                data_source
            )
            VALUES (?, ?, 1440, ?, ?, ?, ?, ?, 'test')
            """,
            [
                (
                    "7203",
                    NOW.isoformat(),
                    3000,
                    3100,
                    2900,
                    3000,
                    1_000_000,
                ),
                (
                    "9984",
                    NOW.isoformat(),
                    12000,
                    12100,
                    11900,
                    12000,
                    100_000,
                ),
            ],
        )
        connection.commit()

    return database


def test_screener_applies_100_share_budget(
    tmp_path: Path,
) -> None:
    database = prepare_database(tmp_path)

    report = UniversePrimaryScreener(
        database_path=database,
        settings=UniverseScreeningSettings(
            maximum_symbols=300,
            maximum_purchase_amount=950_000,
        ),
        now_provider=lambda: NOW,
    ).screen()

    assert report.universe_count == 2
    assert report.evaluated_count == 2
    assert report.selected_count == 1
    assert report.selected[0].code == "7203"
    excluded = next(
        item
        for item in report.excluded
        if item.code == "9984"
    )
    assert "over_purchase_budget" in (
        excluded.exclusion_reasons
    )
