"""Sprint 118 強制決済約定のFIFO損益テスト。"""

import sqlite3
from pathlib import Path

from app.dashboard.dashboard_strategy_service import (
    DashboardStrategyService,
)


def test_end_of_day_exit_is_attributed_to_entry_strategy(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "katana.db"

    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE trade_signals (
                signal_id TEXT PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                action TEXT NOT NULL
            );

            CREATE TABLE trade_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT NOT NULL,
                signal_id TEXT NOT NULL,
                code TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                execution_price REAL NOT NULL,
                executed_at TEXT NOT NULL,
                commission REAL NOT NULL,
                slippage REAL NOT NULL
            );
            """
        )
        connection.executemany(
            """
            INSERT INTO trade_signals (
                signal_id,
                strategy_name,
                action
            )
            VALUES (?, ?, ?)
            """,
            (
                (
                    "entry",
                    "opening-range-breakout-v2",
                    "buy",
                ),
                (
                    "exit",
                    "end-of-day-liquidation",
                    "exit",
                ),
            ),
        )
        connection.executemany(
            """
            INSERT INTO trade_executions (
                execution_id,
                signal_id,
                code,
                side,
                quantity,
                execution_price,
                executed_at,
                commission,
                slippage
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    "e1",
                    "entry",
                    "7203",
                    "buy",
                    100,
                    1000.0,
                    "2026-08-06T00:10:00+00:00",
                    0.0,
                    0.0,
                ),
                (
                    "e2",
                    "exit",
                    "7203",
                    "sell",
                    100,
                    1010.0,
                    "2026-08-06T06:30:00+00:00",
                    0.0,
                    0.0,
                ),
            ),
        )
        connection.commit()

        analysis = (
            DashboardStrategyService
            ._analyze_executions(connection)
        )

    assert len(analysis) == 1
    assert analysis[0]["execution_id"] == "e2"
    assert analysis[0]["realized_profit_loss"] == 1000.0
    assert analysis[0]["pnl_by_entry_strategy"] == {
        "opening-range-breakout-v2": 1000.0
    }
