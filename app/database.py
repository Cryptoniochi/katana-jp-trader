"""SQLiteデータベースの初期化処理。"""

import sqlite3
from pathlib import Path


def initialize_database(database_path: Path) -> None:
    """KATANA用SQLiteデータベースを初期化する。"""

    database_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                id INTEGER PRIMARY KEY,
                version INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                traded_at TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(code, traded_at)
            )
            """
        )

        existing_version = connection.execute(
            "SELECT version FROM schema_version WHERE id = 1"
        ).fetchone()

        if existing_version is None:
            connection.execute(
                """
                INSERT INTO schema_version (id, version)
                VALUES (1, 1)
                """
            )

        connection.commit()
