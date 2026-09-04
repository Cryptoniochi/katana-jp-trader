"""Day-Trade Opportunity Universeのテスト。"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.universe.listed_symbol_csv_importer import ListedSymbolCsvImporter
from app.universe.universe_models import UniverseScreeningSettings
from app.universe.universe_primary_screener import UniversePrimaryScreener


NOW = datetime(2026, 8, 3, tzinfo=timezone.utc)


def _prepare_symbols(tmp_path: Path, rows: list[str]) -> Path:
    database = tmp_path / "katana.db"
    csv_path = tmp_path / "symbols.csv"
    csv_path.write_text(
        "\n".join(
            ["code,name,market,security_type,trading_unit", *rows]
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
        connection.commit()
    return database


def _insert_series(
    database: Path,
    code: str,
    *,
    base_price: float,
    daily_range: float,
    latest_volume_multiplier: float,
    daily_return: float = 0.0,
) -> None:
    rows = []
    for age in reversed(range(10)):
        index = 9 - age
        close = base_price * ((1.0 + daily_return) ** index)
        half = daily_range / 2.0
        volume = 100_000
        if age == 0:
            volume = int(volume * latest_volume_multiplier)
        rows.append(
            (
                code,
                (NOW - timedelta(days=age)).isoformat(),
                close,
                close * (1.0 + half),
                close * (1.0 - half),
                close,
                volume,
            )
        )
    with sqlite3.connect(database) as connection:
        connection.executemany(
            """
            INSERT INTO market_bars (
                code, traded_at, interval_minutes,
                open, high, low, close, volume, data_source
            )
            VALUES (?, ?, 1440, ?, ?, ?, ?, ?, 'test')
            """,
            rows,
        )
        connection.commit()


def test_active_midcap_outranks_static_high_liquidity_name(tmp_path: Path) -> None:
    database = _prepare_symbols(
        tmp_path,
        [
            "1111,StaticMega,Prime,common_stock,100",
            "2222,ActiveMid,Standard,common_stock,100",
        ],
    )
    _insert_series(
        database,
        "1111",
        base_price=3000,
        daily_range=0.008,
        latest_volume_multiplier=1.0,
    )
    _insert_series(
        database,
        "2222",
        base_price=1200,
        daily_range=0.04,
        latest_volume_multiplier=2.0,
        daily_return=0.01,
    )

    report = UniversePrimaryScreener(
        database_path=database,
        settings=UniverseScreeningSettings(
            maximum_symbols=1,
            minimum_average_turnover=1_000_000,
            minimum_average_volume=1_000,
        ),
        now_provider=lambda: NOW,
    ).screen()

    assert report.selected_count == 1
    assert report.selected[0].code == "2222"
    assert report.selected[0].atr_ratio > report.excluded[0].atr_ratio
    assert report.selected[0].volume_ratio > 1.0


def test_opportunity_metrics_are_exposed_in_report(tmp_path: Path) -> None:
    database = _prepare_symbols(
        tmp_path,
        ["3333,Opportunity,Prime,common_stock,100"],
    )
    _insert_series(
        database,
        "3333",
        base_price=1500,
        daily_range=0.03,
        latest_volume_multiplier=1.8,
        daily_return=0.005,
    )

    report = UniversePrimaryScreener(
        database_path=database,
        settings=UniverseScreeningSettings(
            minimum_average_turnover=1_000_000,
            minimum_average_volume=1_000,
        ),
        now_provider=lambda: NOW,
    ).screen()
    item = report.selected[0]

    assert item.opportunity_score == item.score
    assert item.atr_ratio > 0.0
    assert item.volume_ratio > 1.0
    assert item.range_expansion_ratio > 0.0
    assert item.liquidity_score >= 0.0
