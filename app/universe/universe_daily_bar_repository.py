"""全市場日足を既存market_barsへ保存する。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.universe.universe_daily_bar_models import (
    UniverseDailyBar,
)


class UniverseDailyBarRepository:
    """market_barsの日足データをUpsertする。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS market_bars (
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
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                uq_market_bars_code_time_interval_source
                ON market_bars (
                    code,
                    traded_at,
                    interval_minutes,
                    data_source
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_market_bars_daily_code_date
                ON market_bars (
                    interval_minutes,
                    code,
                    traded_at
                )
                """
            )
            connection.commit()

    def upsert_many(
        self,
        bars: tuple[UniverseDailyBar, ...],
    ) -> int:
        self.initialize()

        rows = [
            (
                bar.code,
                datetime.combine(
                    bar.trading_date,
                    datetime.min.time(),
                    tzinfo=timezone.utc,
                ).isoformat(),
                1440,
                bar.open_price,
                bar.high_price,
                bar.low_price,
                bar.close_price,
                bar.volume,
                bar.data_source,
            )
            for bar in bars
        ]

        with sqlite3.connect(self.database_path) as connection:
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (
                    code,
                    traded_at,
                    interval_minutes,
                    data_source
                )
                DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume
                """,
                rows,
            )
            connection.commit()

        return len(rows)
