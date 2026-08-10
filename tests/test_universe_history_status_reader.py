"""Universe History Coverage Readerのテスト。"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.dashboard.universe_history_status_reader import (
    UniverseHistoryStatusReader,
)


NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


def _create_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE listed_symbols (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                market TEXT NOT NULL,
                security_type TEXT NOT NULL,
                is_active INTEGER NOT NULL
            );

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
            );
            """
        )

        for code in ("1001", "1002", "1003", "1004", "1005"):
            connection.execute(
                """
                INSERT INTO listed_symbols (
                    code, name, market, security_type, is_active
                )
                VALUES (?, ?, 'Prime', 'common_stock', 1)
                """,
                (code, f"Name {code}"),
            )

        for code, days in (
            ("1001", 0),
            ("1002", 1),
            ("1003", 5),
            ("1004", 10),
            ("1005", 20),
        ):
            for index in range(days):
                connection.execute(
                    """
                    INSERT INTO market_bars (
                        code, traded_at, interval_minutes,
                        open, high, low, close, volume, data_source
                    )
                    VALUES (?, ?, 1440, 100, 110, 90, 105, 1000, 'test')
                    """,
                    (
                        code,
                        f"2026-07-{index + 1:02d}T00:00:00+00:00",
                    ),
                )
        connection.commit()


def test_universe_history_coverage(tmp_path: Path) -> None:
    database = tmp_path / "katana.db"
    _create_database(database)

    payload = UniverseHistoryStatusReader(
        database,
        now_provider=lambda: NOW,
    ).read()

    assert payload["available"] is True
    assert payload["active_universe_count"] == 5
    assert payload["symbols_with_1_day"] == 4
    assert payload["symbols_with_5_days"] == 3
    assert payload["symbols_with_10_days"] == 2
    assert payload["symbols_with_20_days"] == 1
    assert payload["no_history_count"] == 1
    assert payload["fallback_count"] == 2
    assert payload["developing_count"] == 1
    assert payload["strict_count"] == 1
    assert payload["coverage_20_days"] == 0.2


def test_missing_database_returns_unavailable(
    tmp_path: Path,
) -> None:
    payload = UniverseHistoryStatusReader(
        tmp_path / "missing.db",
        now_provider=lambda: NOW,
    ).read()

    assert payload["available"] is False
    assert payload["active_universe_count"] == 0
