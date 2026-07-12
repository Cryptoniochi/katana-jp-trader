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