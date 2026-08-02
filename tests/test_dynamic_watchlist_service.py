"""DynamicWatchlistServiceのテスト。"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.dynamic_watchlist.dynamic_watchlist_models import (
    DynamicWatchlistSettings,
)
from app.dynamic_watchlist.dynamic_watchlist_service import (
    DynamicWatchlistService,
)


NOW = datetime(
    2026,
    8,
    3,
    0,
    0,
    tzinfo=timezone.utc,
)


def create_database(
    path: Path,
) -> None:
    with sqlite3.connect(path) as connection:
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

        for code, base_price, volume in (
            ("1111", 3_000.0, 500_000),
            ("2222", 11_000.0, 500_000),
            ("3333", 2_000.0, 1_000),
        ):
            for index in range(25):
                price = base_price * (
                    1.0 + index * 0.004
                )
                traded_at = (
                    NOW - timedelta(days=25 - index)
                )
                connection.execute(
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
                    (
                        code,
                        traded_at.isoformat(),
                        price,
                        price * 1.02,
                        price * 0.98,
                        price,
                        volume,
                    ),
                )
        connection.commit()


def test_dry_run_does_not_replace_watchlist(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    watchlist = tmp_path / "watchlist.txt"
    create_database(database)
    watchlist.write_text(
        "9999\n",
        encoding="utf-8",
    )

    result = DynamicWatchlistService(
        database_path=database,
        watchlist_path=watchlist,
        report_directory=tmp_path / "reports",
        settings=DynamicWatchlistSettings(
            minimum_symbols=1,
            minimum_average_turnover=1_000_000,
            minimum_average_volume=10_000,
        ),
        now_provider=lambda: NOW,
    ).generate(
        apply=False
    )

    assert not result.applied
    assert watchlist.read_text(
        encoding="utf-8"
    ) == "9999\n"
    assert [item.code for item in result.selected] == [
        "1111"
    ]
    assert result.selected[0].selection_tier in {
        "strict",
        "fallback",
    }


def test_purchase_budget_excludes_expensive_stock(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    create_database(database)

    result = DynamicWatchlistService(
        database_path=database,
        watchlist_path=tmp_path / "watchlist.txt",
        report_directory=tmp_path / "reports",
        settings=DynamicWatchlistSettings(
            minimum_symbols=1,
            minimum_average_turnover=1_000_000,
            minimum_average_volume=10_000,
        ),
        now_provider=lambda: NOW,
    ).generate()

    assert "2222" not in {
        item.code
        for item in result.selected
    }


def test_apply_creates_backup_and_updates_watchlist(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    watchlist = tmp_path / "watchlist.txt"
    create_database(database)
    watchlist.write_text(
        "9999\n",
        encoding="utf-8",
    )

    result = DynamicWatchlistService(
        database_path=database,
        watchlist_path=watchlist,
        report_directory=tmp_path / "reports",
        settings=DynamicWatchlistSettings(
            minimum_symbols=1,
            minimum_average_turnover=1_000_000,
            minimum_average_volume=10_000,
        ),
        now_provider=lambda: NOW,
    ).generate(
        apply=True
    )

    assert result.applied
    assert watchlist.read_text(
        encoding="utf-8"
    ) == "1111\n"
    assert result.backup_path is not None
    assert Path(result.backup_path).exists()



def test_short_history_uses_fallback_tier(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"

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
        for index in range(5):
            price = 2_000 + index * 20
            connection.execute(
                """
                INSERT INTO market_bars (
                    code, traded_at, interval_minutes,
                    open, high, low, close, volume, data_source
                )
                VALUES (?, ?, 1440, ?, ?, ?, ?, ?, 'kabu-station')
                """,
                (
                    "4444",
                    (
                        NOW - timedelta(days=5 - index)
                    ).isoformat(),
                    price,
                    price * 1.01,
                    price * 0.99,
                    price,
                    100_000,
                ),
            )
        connection.commit()

    result = DynamicWatchlistService(
        database_path=database,
        watchlist_path=tmp_path / "watchlist.txt",
        report_directory=tmp_path / "reports",
        settings=DynamicWatchlistSettings(
            minimum_symbols=1,
            minimum_average_turnover=50_000_000,
            minimum_average_volume=50_000,
            fallback_minimum_average_turnover=1_000_000,
            fallback_minimum_average_volume=1_000,
        ),
        now_provider=lambda: NOW,
    ).generate()

    assert [item.code for item in result.selected] == [
        "4444"
    ]
    assert result.selected[0].selection_tier == "fallback"
