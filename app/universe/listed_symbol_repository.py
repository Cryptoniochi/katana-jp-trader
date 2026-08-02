"""上場銘柄マスターのSQLite Repository。"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from app.universe.universe_models import (
    ListedSymbol,
)


class ListedSymbolRepository:
    """listed_symbolsテーブルを管理する。"""

    def __init__(
        self,
        database_path: Path,
    ) -> None:
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with sqlite3.connect(
            self.database_path
        ) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS listed_symbols (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    market TEXT NOT NULL,
                    security_type TEXT NOT NULL,
                    trading_unit INTEGER NOT NULL,
                    listed_date TEXT,
                    delisted_date TEXT,
                    is_active INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_listed_symbols_active_market
                ON listed_symbols (
                    is_active,
                    market,
                    security_type
                )
                """
            )
            connection.commit()

    def upsert_many(
        self,
        symbols: tuple[ListedSymbol, ...],
    ) -> None:
        self.initialize()

        with sqlite3.connect(
            self.database_path
        ) as connection:
            connection.executemany(
                """
                INSERT INTO listed_symbols (
                    code,
                    name,
                    market,
                    security_type,
                    trading_unit,
                    listed_date,
                    delisted_date,
                    is_active,
                    source,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    market = excluded.market,
                    security_type = excluded.security_type,
                    trading_unit = excluded.trading_unit,
                    listed_date = excluded.listed_date,
                    delisted_date = excluded.delisted_date,
                    is_active = excluded.is_active,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                [
                    (
                        item.code,
                        item.name,
                        item.market,
                        item.security_type,
                        item.trading_unit,
                        (
                            item.listed_date.isoformat()
                            if item.listed_date
                            else None
                        ),
                        (
                            item.delisted_date.isoformat()
                            if item.delisted_date
                            else None
                        ),
                        int(item.is_active),
                        item.source,
                        item.updated_at.isoformat(),
                    )
                    for item in symbols
                ],
            )
            connection.commit()

    def load_active(
        self,
        *,
        allowed_markets: tuple[str, ...],
        allowed_security_types: tuple[str, ...],
    ) -> tuple[ListedSymbol, ...]:
        self.initialize()

        market_placeholders = ",".join(
            "?"
            for _ in allowed_markets
        )
        type_placeholders = ",".join(
            "?"
            for _ in allowed_security_types
        )

        query = f"""
            SELECT
                code,
                name,
                market,
                security_type,
                trading_unit,
                listed_date,
                delisted_date,
                is_active,
                source,
                updated_at
            FROM listed_symbols
            WHERE is_active = 1
              AND market IN ({market_placeholders})
              AND security_type IN ({type_placeholders})
            ORDER BY code ASC
        """

        with sqlite3.connect(
            self.database_path
        ) as connection:
            rows = connection.execute(
                query,
                (
                    *allowed_markets,
                    *allowed_security_types,
                ),
            ).fetchall()

        return tuple(
            ListedSymbol(
                code=str(row[0]),
                name=str(row[1]),
                market=str(row[2]),
                security_type=str(row[3]),
                trading_unit=int(row[4]),
                listed_date=(
                    date.fromisoformat(str(row[5]))
                    if row[5]
                    else None
                ),
                delisted_date=(
                    date.fromisoformat(str(row[6]))
                    if row[6]
                    else None
                ),
                is_active=bool(row[7]),
                source=str(row[8]),
                updated_at=datetime.fromisoformat(
                    str(row[9])
                ),
            )
            for row in rows
        )
