"""Dynamic WatchlistへのLearning Feedback統合テスト。"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.dynamic_watchlist.dynamic_watchlist_models import (
    DynamicWatchlistSettings,
)
from app.dynamic_watchlist.dynamic_watchlist_service import (
    DynamicWatchlistService,
)


NOW = datetime(2026, 8, 3, tzinfo=timezone.utc)


def prepare_database(database: Path) -> None:
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
            price = 3000.0 + index * 10
            connection.execute(
                """
                INSERT INTO market_bars (
                    code, traded_at, interval_minutes,
                    open, high, low, close, volume, data_source
                )
                VALUES (?, ?, 1440, ?, ?, ?, ?, ?, 'kabu-station')
                """,
                (
                    "7203",
                    (
                        NOW - timedelta(days=25-index)
                    ).isoformat(),
                    price,
                    price * 1.01,
                    price * 0.99,
                    price,
                    500000,
                ),
            )

        connection.execute(
            """
            CREATE TABLE strategy_learning_summary (
                code TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                trade_count INTEGER NOT NULL,
                win_count INTEGER NOT NULL,
                loss_count INTEGER NOT NULL,
                breakeven_count INTEGER NOT NULL,
                win_rate REAL,
                gross_profit REAL NOT NULL,
                gross_loss REAL NOT NULL,
                net_profit_loss REAL NOT NULL,
                profit_factor REAL,
                expectancy REAL,
                average_return_rate REAL,
                average_holding_minutes REAL,
                sample_confidence REAL NOT NULL,
                historical_score REAL NOT NULL,
                eligible_for_feedback INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (code, strategy_name)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO strategy_learning_summary
            VALUES (
                '7203',
                'pullback-breakout-v1',
                12, 8, 4, 0, 0.6667,
                40000, -8000, 32000, 5.0,
                2666.67, 0.01, 30,
                0.4, 12.0, 1, ?
            )
            """,
            (NOW.isoformat(),),
        )
        connection.commit()


def test_learning_bonus_is_added_to_total_score(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    prepare_database(database)

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

    assert candidate.learning_applied
    assert candidate.historical_score == 12.0
    assert candidate.historical_trade_count == 12
    assert candidate.learned_preferred_strategy == (
        "pullback"
    )
    assert candidate.total_score >= (
        candidate.technical_score
    )
    assert candidate.total_score <= 100.0


def test_learning_can_be_disabled(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    prepare_database(database)

    result = DynamicWatchlistService(
        database_path=database,
        watchlist_path=tmp_path / "watchlist.txt",
        report_directory=tmp_path / "reports",
        settings=DynamicWatchlistSettings(
            minimum_symbols=1,
            minimum_average_turnover=1_000_000,
            minimum_average_volume=1_000,
            learning_feedback_enabled=False,
        ),
        now_provider=lambda: NOW,
    ).generate()

    candidate = result.selected[0]

    assert not candidate.learning_applied
    assert candidate.historical_score == 0.0
    assert candidate.total_score == (
        candidate.technical_score
    )
