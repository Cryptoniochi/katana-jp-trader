"""SQLiteデータベースの初期化とマイグレーション処理。"""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 9


def initialize_database(
    database_path: Path,
) -> None:
    """KATANA用SQLiteデータベースを初期化する。"""

    database_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        _create_schema_version_table(connection)
        _migrate_schema_version_table(connection)

        _create_stock_prices_table(connection)

        _create_market_bars_table(connection)
        _migrate_market_bars_table(connection)
        _create_market_bar_indexes(connection)

        _create_update_runs_table(connection)
        _migrate_update_runs_table(connection)
        _create_update_run_indexes(connection)

        _create_trade_signals_table(connection)
        _migrate_trade_signals_table(connection)
        _create_trade_signal_indexes(connection)

        _create_trade_orders_table(connection)
        _migrate_trade_orders_table(connection)
        _create_trade_order_indexes(connection)

        _create_scheduled_run_states_table(connection)
        _migrate_scheduled_run_states_table(connection)
        _create_scheduled_run_state_indexes(connection)

        _create_trade_executions_table(connection)
        _migrate_trade_executions_table(connection)
        _create_trade_execution_indexes(connection)

        _create_positions_table(connection)
        _migrate_positions_table(connection)
        _create_position_indexes(connection)

        _create_position_applied_executions_table(connection)
        _create_position_applied_execution_indexes(connection)

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

    count_columns = (
        "requested_code_count",
        "updated_code_count",
        "skipped_code_count",
        "failed_code_count",
        "business_date_count",
        "request_count",
        "successful_request_count",
        "empty_request_count",
        "failed_request_count",
        "processed_bar_count",
    )

    for column_name in count_columns:
        connection.execute(
            f"""
            UPDATE update_runs
            SET {column_name} = 0
            WHERE {column_name} IS NULL
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


def _create_trade_signals_table(
    connection: sqlite3.Connection,
) -> None:
    """売買シグナルを保存するテーブルを作成する。"""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT NOT NULL UNIQUE,
            code TEXT NOT NULL,
            strategy_name TEXT NOT NULL,
            action TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            signal_price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            reason TEXT NOT NULL,
            confidence REAL,
            metadata_json TEXT NOT NULL
                DEFAULT '{}',
            status TEXT NOT NULL
                DEFAULT 'pending',
            processed_at TEXT,
            process_note TEXT,
            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(
                code,
                strategy_name,
                action,
                generated_at
            )
        )
        """
    )


def _migrate_trade_signals_table(
    connection: sqlite3.Connection,
) -> None:
    """既存trade_signalsへ不足している列を追加する。"""

    column_definitions = {
        "signal_id": "TEXT",
        "code": "TEXT",
        "strategy_name": "TEXT",
        "action": "TEXT",
        "generated_at": "TEXT",
        "signal_price": "REAL",
        "quantity": "INTEGER",
        "reason": "TEXT",
        "confidence": "REAL",
        "metadata_json": "TEXT DEFAULT '{}'",
        "status": "TEXT DEFAULT 'pending'",
        "processed_at": "TEXT",
        "process_note": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    }

    for column_name, column_definition in column_definitions.items():
        _add_column_if_missing(
            connection=connection,
            table_name="trade_signals",
            column_name=column_name,
            column_definition=column_definition,
        )

    connection.execute(
        """
        UPDATE trade_signals
        SET metadata_json = '{}'
        WHERE metadata_json IS NULL
           OR TRIM(metadata_json) = ''
        """
    )

    connection.execute(
        """
        UPDATE trade_signals
        SET status = 'pending'
        WHERE status IS NULL
           OR TRIM(status) = ''
        """
    )

    connection.execute(
        """
        UPDATE trade_signals
        SET created_at = CURRENT_TIMESTAMP
        WHERE created_at IS NULL
        """
    )

    connection.execute(
        """
        UPDATE trade_signals
        SET updated_at = CURRENT_TIMESTAMP
        WHERE updated_at IS NULL
        """
    )


def _create_trade_signal_indexes(
    connection: sqlite3.Connection,
) -> None:
    """売買シグナル検索用のインデックスを作成する。"""

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_trade_signals_signal_id
        ON trade_signals (
            signal_id
        )
        """
    )

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_trade_signals_identity
        ON trade_signals (
            code,
            strategy_name,
            action,
            generated_at
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_trade_signals_status_generated_at
        ON trade_signals (
            status,
            generated_at DESC
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_trade_signals_code_generated_at
        ON trade_signals (
            code,
            generated_at DESC
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_trade_signals_strategy_generated_at
        ON trade_signals (
            strategy_name,
            generated_at DESC
        )
        """
    )


def _create_trade_orders_table(
    connection: sqlite3.Connection,
) -> None:
    """証券会社へ送信する注文の永続化テーブルを作成する。"""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL UNIQUE,
            signal_id TEXT NOT NULL UNIQUE,
            code TEXT NOT NULL,
            side TEXT NOT NULL,
            order_type TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            limit_price REAL,
            stop_price REAL,
            status TEXT NOT NULL
                DEFAULT 'new',
            filled_quantity INTEGER NOT NULL
                DEFAULT 0,
            average_fill_price REAL,
            broker_order_id TEXT,
            status_reason TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            submitted_at TEXT,
            completed_at TEXT,
            FOREIGN KEY(signal_id)
                REFERENCES trade_signals(signal_id)
        )
        """
    )


def _migrate_trade_orders_table(
    connection: sqlite3.Connection,
) -> None:
    """既存trade_ordersへ不足している列を追加する。"""

    column_definitions = {
        "order_id": "TEXT",
        "signal_id": "TEXT",
        "code": "TEXT",
        "side": "TEXT",
        "order_type": "TEXT",
        "quantity": "INTEGER",
        "limit_price": "REAL",
        "stop_price": "REAL",
        "status": "TEXT DEFAULT 'new'",
        "filled_quantity": "INTEGER DEFAULT 0",
        "average_fill_price": "REAL",
        "broker_order_id": "TEXT",
        "status_reason": "TEXT",
        "error_message": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
        "submitted_at": "TEXT",
        "completed_at": "TEXT",
    }

    for column_name, column_definition in column_definitions.items():
        _add_column_if_missing(
            connection=connection,
            table_name="trade_orders",
            column_name=column_name,
            column_definition=column_definition,
        )

    connection.execute(
        """
        UPDATE trade_orders
        SET status = 'new'
        WHERE status IS NULL
           OR TRIM(status) = ''
        """
    )

    connection.execute(
        """
        UPDATE trade_orders
        SET filled_quantity = 0
        WHERE filled_quantity IS NULL
        """
    )

    connection.execute(
        """
        UPDATE trade_orders
        SET created_at = CURRENT_TIMESTAMP
        WHERE created_at IS NULL
        """
    )

    connection.execute(
        """
        UPDATE trade_orders
        SET updated_at = CURRENT_TIMESTAMP
        WHERE updated_at IS NULL
        """
    )


def _create_trade_order_indexes(
    connection: sqlite3.Connection,
) -> None:
    """注文検索用のインデックスを作成する。"""

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_trade_orders_order_id
        ON trade_orders (
            order_id
        )
        """
    )

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_trade_orders_signal_id
        ON trade_orders (
            signal_id
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_trade_orders_status_created_at
        ON trade_orders (
            status,
            created_at DESC
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_trade_orders_code_created_at
        ON trade_orders (
            code,
            created_at DESC
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_trade_orders_broker_order_id
        ON trade_orders (
            broker_order_id
        )
        """
    )


def _create_scheduled_run_states_table(
    connection: sqlite3.Connection,
) -> None:
    """定刻処理の完了状態を保存するテーブルを作成する。"""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_run_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trading_date TEXT NOT NULL,
            process_name TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(
                trading_date,
                process_name
            )
        )
        """
    )


def _migrate_scheduled_run_states_table(
    connection: sqlite3.Connection,
) -> None:
    """既存scheduled_run_statesへ不足列を追加する。"""

    column_definitions = {
        "trading_date": "TEXT",
        "process_name": "TEXT",
        "completed_at": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    }

    for column_name, column_definition in column_definitions.items():
        _add_column_if_missing(
            connection=connection,
            table_name="scheduled_run_states",
            column_name=column_name,
            column_definition=column_definition,
        )

    connection.execute(
        """
        UPDATE scheduled_run_states
        SET created_at = CURRENT_TIMESTAMP
        WHERE created_at IS NULL
        """
    )

    connection.execute(
        """
        UPDATE scheduled_run_states
        SET updated_at = CURRENT_TIMESTAMP
        WHERE updated_at IS NULL
        """
    )


def _create_scheduled_run_state_indexes(
    connection: sqlite3.Connection,
) -> None:
    """定刻実行状態検索用のインデックスを作成する。"""

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_scheduled_run_states_identity
        ON scheduled_run_states (
            trading_date,
            process_name
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_scheduled_run_states_completed_at
        ON scheduled_run_states (
            completed_at DESC
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_scheduled_run_states_process_date
        ON scheduled_run_states (
            process_name,
            trading_date DESC
        )
        """
    )



def _create_trade_executions_table(
    connection: sqlite3.Connection,
) -> None:
    """Brokerで成立した約定履歴テーブルを作成する。"""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id TEXT NOT NULL UNIQUE,
            signal_id TEXT NOT NULL,
            order_id TEXT NOT NULL,
            broker_order_id TEXT NOT NULL,
            code TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            execution_price REAL NOT NULL,
            executed_at TEXT NOT NULL,
            broker_name TEXT NOT NULL,
            commission REAL NOT NULL DEFAULT 0,
            slippage REAL NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(signal_id)
                REFERENCES trade_signals(signal_id),
            FOREIGN KEY(order_id)
                REFERENCES trade_orders(order_id)
        )
        """
    )


def _migrate_trade_executions_table(
    connection: sqlite3.Connection,
) -> None:
    """既存trade_executionsへ不足している列を追加する。"""

    column_definitions = {
        "execution_id": "TEXT",
        "signal_id": "TEXT",
        "order_id": "TEXT",
        "broker_order_id": "TEXT",
        "code": "TEXT",
        "side": "TEXT",
        "quantity": "INTEGER",
        "execution_price": "REAL",
        "executed_at": "TEXT",
        "broker_name": "TEXT",
        "commission": "REAL DEFAULT 0",
        "slippage": "REAL DEFAULT 0",
        "metadata_json": "TEXT DEFAULT '{}'",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    }

    for column_name, column_definition in column_definitions.items():
        _add_column_if_missing(
            connection=connection,
            table_name="trade_executions",
            column_name=column_name,
            column_definition=column_definition,
        )

    connection.execute(
        """
        UPDATE trade_executions
        SET commission = 0
        WHERE commission IS NULL
        """
    )
    connection.execute(
        """
        UPDATE trade_executions
        SET slippage = 0
        WHERE slippage IS NULL
        """
    )
    connection.execute(
        """
        UPDATE trade_executions
        SET metadata_json = '{}'
        WHERE metadata_json IS NULL
           OR TRIM(metadata_json) = ''
        """
    )
    connection.execute(
        """
        UPDATE trade_executions
        SET created_at = CURRENT_TIMESTAMP
        WHERE created_at IS NULL
        """
    )
    connection.execute(
        """
        UPDATE trade_executions
        SET updated_at = CURRENT_TIMESTAMP
        WHERE updated_at IS NULL
        """
    )


def _create_trade_execution_indexes(
    connection: sqlite3.Connection,
) -> None:
    """約定履歴検索用のインデックスを作成する。"""

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_trade_executions_execution_id
        ON trade_executions (
            execution_id
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_trade_executions_order_executed_at
        ON trade_executions (
            order_id,
            executed_at DESC
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_trade_executions_signal_executed_at
        ON trade_executions (
            signal_id,
            executed_at DESC
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_trade_executions_code_executed_at
        ON trade_executions (
            code,
            executed_at DESC
        )
        """
    )


def _create_positions_table(
    connection: sqlite3.Connection,
) -> None:
    """現在保有ポジションテーブルを作成する。"""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id TEXT NOT NULL UNIQUE,
            code TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            average_cost REAL NOT NULL,
            realized_profit_loss REAL NOT NULL DEFAULT 0,
            opened_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(
                code,
                side
            )
        )
        """
    )


def _migrate_positions_table(
    connection: sqlite3.Connection,
) -> None:
    """既存positionsへ不足している列を追加する。"""

    column_definitions = {
        "position_id": "TEXT",
        "code": "TEXT",
        "side": "TEXT",
        "quantity": "INTEGER",
        "average_cost": "REAL",
        "realized_profit_loss": "REAL DEFAULT 0",
        "opened_at": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    }

    for column_name, column_definition in column_definitions.items():
        _add_column_if_missing(
            connection=connection,
            table_name="positions",
            column_name=column_name,
            column_definition=column_definition,
        )

    connection.execute(
        """
        UPDATE positions
        SET realized_profit_loss = 0
        WHERE realized_profit_loss IS NULL
        """
    )
    connection.execute(
        """
        UPDATE positions
        SET created_at = CURRENT_TIMESTAMP
        WHERE created_at IS NULL
        """
    )
    connection.execute(
        """
        UPDATE positions
        SET updated_at = CURRENT_TIMESTAMP
        WHERE updated_at IS NULL
        """
    )


def _create_position_indexes(
    connection: sqlite3.Connection,
) -> None:
    """現在ポジション検索用のインデックスを作成する。"""

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_positions_position_id
        ON positions (
            position_id
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_positions_code_side
        ON positions (
            code,
            side
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_positions_updated_at
        ON positions (
            updated_at DESC
        )
        """
    )


def _create_position_applied_executions_table(
    connection: sqlite3.Connection,
) -> None:
    """ポジションへ反映済みの約定IDを保存する。"""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS position_applied_executions (
            execution_id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL,
            FOREIGN KEY(execution_id)
                REFERENCES trade_executions(execution_id)
        )
        """
    )


def _create_position_applied_execution_indexes(
    connection: sqlite3.Connection,
) -> None:
    """反映済み約定の検索用インデックスを作成する。"""

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_position_applied_executions_applied_at
        ON position_applied_executions (
            applied_at DESC
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