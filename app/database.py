"""SQLiteデータベースの初期化とマイグレーション処理。"""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 3


def initialize_database(
    database_path: Path,
) -> None:
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

        _create_update_runs_table(connection)
        _migrate_update_runs_table(connection)
        _create_update_run_indexes(connection)

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


def _create_update_runs_table(
    connection: sqlite3.Connection,
) -> None:
    """J-Quants自動更新の実行履歴テーブルを作成する。"""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS update_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL UNIQUE,
            process_name TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            exit_code INTEGER,
            requested_code_count INTEGER NOT NULL
                DEFAULT 0,
            updated_code_count INTEGER NOT NULL
                DEFAULT 0,
            skipped_code_count INTEGER NOT NULL
                DEFAULT 0,
            failed_code_count INTEGER NOT NULL
                DEFAULT 0,
            business_date_count INTEGER NOT NULL
                DEFAULT 0,
            request_count INTEGER NOT NULL
                DEFAULT 0,
            successful_request_count INTEGER NOT NULL
                DEFAULT 0,
            empty_request_count INTEGER NOT NULL
                DEFAULT 0,
            failed_request_count INTEGER NOT NULL
                DEFAULT 0,
            processed_bar_count INTEGER NOT NULL
                DEFAULT 0,
            error_message TEXT,
            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _migrate_update_runs_table(
    connection: sqlite3.Connection,
) -> None:
    """既存update_runsへ不足している列を追加する。"""

    column_definitions = {
        "run_id": "TEXT",
        "process_name": "TEXT",
        "status": "TEXT",
        "started_at": "TEXT",
        "finished_at": "TEXT",
        "exit_code": "INTEGER",
        "requested_code_count": "INTEGER DEFAULT 0",
        "updated_code_count": "INTEGER DEFAULT 0",
        "skipped_code_count": "INTEGER DEFAULT 0",
        "failed_code_count": "INTEGER DEFAULT 0",
        "business_date_count": "INTEGER DEFAULT 0",
        "request_count": "INTEGER DEFAULT 0",
        "successful_request_count": "INTEGER DEFAULT 0",
        "empty_request_count": "INTEGER DEFAULT 0",
        "failed_request_count": "INTEGER DEFAULT 0",
        "processed_bar_count": "INTEGER DEFAULT 0",
        "error_message": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    }

    for column_name, column_definition in column_definitions.items():
        _add_column_if_missing(
            connection=connection,
            table_name="update_runs",
            column_name=column_name,
            column_definition=column_definition,
        )

    connection.execute(
        """
        UPDATE update_runs
        SET requested_code_count = 0
        WHERE requested_code_count IS NULL
        """
    )

    connection.execute(
        """
        UPDATE update_runs
        SET updated_code_count = 0
        WHERE updated_code_count IS NULL
        """
    )

    connection.execute(
        """
        UPDATE update_runs
        SET skipped_code_count = 0
        WHERE skipped_code_count IS NULL
        """
    )

    connection.execute(
        """
        UPDATE update_runs
        SET failed_code_count = 0
        WHERE failed_code_count IS NULL
        """
    )

    connection.execute(
        """
        UPDATE update_runs
        SET business_date_count = 0
        WHERE business_date_count IS NULL
        """
    )

    connection.execute(
        """
        UPDATE update_runs
        SET request_count = 0
        WHERE request_count IS NULL
        """
    )

    connection.execute(
        """
        UPDATE update_runs
        SET successful_request_count = 0
        WHERE successful_request_count IS NULL
        """
    )

    connection.execute(
        """
        UPDATE update_runs
        SET empty_request_count = 0
        WHERE empty_request_count IS NULL
        """
    )

    connection.execute(
        """
        UPDATE update_runs
        SET failed_request_count = 0
        WHERE failed_request_count IS NULL
        """
    )

    connection.execute(
        """
        UPDATE update_runs
        SET processed_bar_count = 0
        WHERE processed_bar_count IS NULL
        """
    )

    connection.execute(
        """
        UPDATE update_runs
        SET created_at = CURRENT_TIMESTAMP
        WHERE created_at IS NULL
        """
    )

    connection.execute(
        """
        UPDATE update_runs
        SET updated_at = CURRENT_TIMESTAMP
        WHERE updated_at IS NULL
        """
    )


def _create_update_run_indexes(
    connection: sqlite3.Connection,
) -> None:
    """自動更新実行履歴用の検索インデックスを作成する。"""

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_update_runs_run_id
        ON update_runs (
            run_id
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_update_runs_started_at
        ON update_runs (
            started_at DESC
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_update_runs_status_started_at
        ON update_runs (
            status,
            started_at DESC
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
        for row in connection.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
    }

    if column_name in existing_columns:
        return

    connection.execute(
        f"""
        ALTER TABLE {table_name}
        ADD COLUMN {column_name} {column_definition}
        """
    )