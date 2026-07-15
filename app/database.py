"""SQLiteデータベースの初期化とマイグレーション処理。"""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2


def initialize_database(database_path: Path) -> None:
    """KATANA用SQLiteデータベースを初期化する。"""

    database_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with sqlite3.connect(database_path) as connection:
        _create_schema_version_table(connection)
        _migrate_schema_version_table(connection)
        _create_stock_prices_table(connection)
        _create_market_bars_table(connection)
        _migrate_market_bars_table(connection)
        _create_market_bar_indexes(connection)
        _update_schema_version(connection)

        connection.commit()


def _create_schema_version_table(
    connection: sqlite3.Connection,
) -> None:
    """スキーマバージョン管理テーブルを作成する。"""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY,
            version INTEGER NOT NULL,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )


def _migrate_schema_version_table(
    connection: sqlite3.Connection,
) -> None:
    """旧schema_versionへ不足している列を追加する。"""

    _add_column_if_missing(
        connection=connection,
        table_name="schema_version",
        column_name="created_at",
        column_definition="TEXT",
    )
    _add_column_if_missing(
        connection=connection,
        table_name="schema_version",
        column_name="updated_at",
        column_definition="TEXT",
    )

    connection.execute(
        """
        UPDATE schema_version
        SET created_at = CURRENT_TIMESTAMP
        WHERE created_at IS NULL
        """
    )

    connection.execute(
        """
        UPDATE schema_version
        SET updated_at = CURRENT_TIMESTAMP
        WHERE updated_at IS NULL
        """
    )


def _create_stock_prices_table(
    connection: sqlite3.Connection,
) -> None:
    """既存互換用の株価テーブルを作成する。"""

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
            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(code, traded_at)
        )
        """
    )


def _create_market_bars_table(
    connection: sqlite3.Connection,
) -> None:
    """時間軸を区別できる市場データテーブルを作成する。"""

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
            data_source TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(
                code,
                traded_at,
                interval_minutes
            )
        )
        """
    )


def _migrate_market_bars_table(
    connection: sqlite3.Connection,
) -> None:
    """既存market_barsへ不足列を追加し、日時を補完する。"""

    _add_column_if_missing(
        connection=connection,
        table_name="market_bars",
        column_name="data_source",
        column_definition="TEXT",
    )
    _add_column_if_missing(
        connection=connection,
        table_name="market_bars",
        column_name="created_at",
        column_definition="TEXT",
    )
    _add_column_if_missing(
        connection=connection,
        table_name="market_bars",
        column_name="updated_at",
        column_definition="TEXT",
    )

    connection.execute(
        """
        UPDATE market_bars
        SET data_source = 'unknown'
        WHERE data_source IS NULL
           OR TRIM(data_source) = ''
        """
    )

    connection.execute(
        """
        UPDATE market_bars
        SET created_at = CURRENT_TIMESTAMP
        WHERE created_at IS NULL
        """
    )

    connection.execute(
        """
        UPDATE market_bars
        SET updated_at = CURRENT_TIMESTAMP
        WHERE updated_at IS NULL
        """
    )


def _create_market_bar_indexes(
    connection: sqlite3.Connection,
) -> None:
    """市場時間足用の検索インデックスを作成する。"""

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_market_bars_code_time
        ON market_bars (
            code,
            traded_at
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_market_bars_interval_time
        ON market_bars (
            interval_minutes,
            traded_at
        )
        """
    )


def _update_schema_version(
    connection: sqlite3.Connection,
) -> None:
    """現在のスキーマバージョンを保存する。"""

    existing_row = connection.execute(
        """
        SELECT id
        FROM schema_version
        WHERE id = 1
        """
    ).fetchone()

    if existing_row is None:
        connection.execute(
            """
            INSERT INTO schema_version (
                id,
                version,
                created_at,
                updated_at
            )
            VALUES (
                1,
                ?,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """,
            (SCHEMA_VERSION,),
        )
        return

    connection.execute(
        """
        UPDATE schema_version
        SET
            version = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
        """,
        (SCHEMA_VERSION,),
    )


def _add_column_if_missing(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    """指定テーブルに存在しない列を追加する。"""

    existing_columns = {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }

    if column_name in existing_columns:
        return

    connection.execute(
        f"""
        ALTER TABLE {table_name}
        ADD COLUMN {column_name} {column_definition}
        """
    )
