"""全市場候補とDynamic Watchlistの接続テスト。"""

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


def create_market_bars(database: Path) -> None:
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

        for code in ("7203", "8306", "9984"):
            for index in range(25):
                price = 1000 + index * 10
                connection.execute(
                    """
                    INSERT INTO market_bars (
                        code, traded_at, interval_minutes,
                        open, high, low, close,
                        volume, data_source
                    )
                    VALUES (?, ?, 1440, ?, ?, ?, ?, ?, 'test')
                    """,
                    (
                        code,
                        (
                            NOW
                            - timedelta(days=25-index)
                        ).isoformat(),
                        price,
                        price * 1.01,
                        price * 0.99,
                        price,
                        1_000_000,
                    ),
                )
        connection.commit()


def test_only_primary_candidates_are_evaluated(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    candidates = tmp_path / "universe_candidates.txt"
    create_market_bars(database)
    candidates.write_text(
        "7203\n8306\n",
        encoding="utf-8",
    )

    result = DynamicWatchlistService(
        database_path=database,
        watchlist_path=tmp_path / "watchlist.txt",
        report_directory=tmp_path / "reports",
        candidate_universe_path=candidates,
        require_candidate_universe=True,
        settings=DynamicWatchlistSettings(
            minimum_symbols=1,
            maximum_symbols=50,
            minimum_average_turnover=1_000_000,
            minimum_average_volume=1_000,
        ),
        now_provider=lambda: NOW,
    ).generate()

    assert result.evaluated_count == 2
    assert {
        item.code
        for item in result.selected
    } <= {"7203", "8306"}


def test_required_candidate_file_must_exist(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    create_market_bars(database)

    service = DynamicWatchlistService(
        database_path=database,
        watchlist_path=tmp_path / "watchlist.txt",
        report_directory=tmp_path / "reports",
        candidate_universe_path=(
            tmp_path / "missing.txt"
        ),
        require_candidate_universe=True,
        settings=DynamicWatchlistSettings(
            minimum_symbols=1,
        ),
        now_provider=lambda: NOW,
    )

    try:
        service.generate()
    except FileNotFoundError:
        pass
    else:
        raise AssertionError(
            "FileNotFoundError was not raised."
        )
