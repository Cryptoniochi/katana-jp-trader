"""Dynamic WatchlistのFeature項目統合テスト。"""

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
    tzinfo=timezone.utc,
)


def test_candidate_contains_strategy_scores(
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
        for index in range(25):
            price = 3_000 + index * 15
            connection.execute(
                """
                INSERT INTO market_bars (
                    code, traded_at, interval_minutes,
                    open, high, low, close, volume, data_source
                )
                VALUES (?, ?, 1440, ?, ?, ?, ?, ?, 'kabu-station')
                """,
                (
                    "6758",
                    (
                        NOW - timedelta(days=25 - index)
                    ).isoformat(),
                    price * 0.995,
                    price * 1.02,
                    price * 0.98,
                    price,
                    500_000 + index * 10_000,
                ),
            )
        connection.commit()

    result = DynamicWatchlistService(
        database_path=database,
        watchlist_path=tmp_path / "watchlist.txt",
        report_directory=tmp_path / "reports",
        settings=DynamicWatchlistSettings(
            minimum_symbols=1,
            minimum_average_turnover=1_000_000,
            minimum_average_volume=1_000,
        ),
        now_provider=lambda: NOW,
    ).generate()

    candidate = result.selected[0]

    assert candidate.rating_tier in {
        "A+",
        "A",
        "B",
        "C",
    }
    assert candidate.preferred_strategy in {
        "orb",
        "pullback",
        "high-breakout",
    }
    assert candidate.orb_score >= 0
    assert candidate.pullback_score >= 0
    assert candidate.high_breakout_score >= 0
