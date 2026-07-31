"""DashboardStrategyServiceのテスト。"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.dashboard.dashboard_strategy_service import (
    DashboardStrategyService,
)


NOW = datetime(
    2026,
    8,
    3,
    12,
    0,
    tzinfo=timezone.utc,
)


def create_database(
    tmp_path: Path,
) -> Path:
    path = tmp_path / "katana.db"

    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE trade_signals (
                id INTEGER PRIMARY KEY,
                signal_id TEXT,
                strategy_name TEXT,
                generated_at TEXT,
                action TEXT
            );

            CREATE TABLE trade_executions (
                id INTEGER PRIMARY KEY,
                execution_id TEXT,
                signal_id TEXT,
                code TEXT,
                side TEXT,
                quantity INTEGER,
                execution_price REAL,
                executed_at TEXT,
                commission REAL,
                slippage REAL
            );

            CREATE TABLE high_breakout_candidates (
                id INTEGER PRIMARY KEY,
                trading_date TEXT
            );
            """
        )

        connection.executemany(
            """
            INSERT INTO trade_signals (
                signal_id,
                strategy_name,
                generated_at,
                action
            )
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    "orb-buy",
                    "opening-range-breakout-v2",
                    "2026-08-03T09:30:00+00:00",
                    "buy",
                ),
                (
                    "orb-exit",
                    "opening-range-breakout-v2",
                    "2026-08-03T10:00:00+00:00",
                    "exit",
                ),
            ],
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
            [
                (
                    "entry",
                    "orb-buy",
                    "7203",
                    "buy",
                    100,
                    1000.0,
                    "2026-08-03T09:30:00+00:00",
                    100.0,
                    0.0,
                ),
                (
                    "exit",
                    "orb-exit",
                    "7203",
                    "sell",
                    100,
                    1020.0,
                    "2026-08-03T10:00:00+00:00",
                    100.0,
                    0.0,
                ),
            ],
        )
        connection.execute(
            """
            INSERT INTO high_breakout_candidates (
                trading_date
            )
            VALUES ('2026-08-03')
            """
        )
        connection.commit()

    return path


def test_service_builds_strategy_summary(
    tmp_path: Path,
) -> None:
    service = DashboardStrategyService(
        create_database(tmp_path),
        now_provider=lambda: NOW,
    )

    payload = service.create_payload(
        trading_date=NOW.date()
    )
    rows = {
        row.strategy_name: row
        for row in payload.strategies
    }

    assert rows["ORB"].signal_count == 2
    assert rows["ORB"].execution_count == 2
    assert rows["ORB"].completed_trade_count == 1
    assert rows["ORB"].win_count == 1
    assert rows["ORB"].net_profit_loss == 1800.0
    assert rows["High Breakout"].candidate_count == 1
    assert len(payload.recent_trades) == 2


def test_service_returns_empty_rows_without_database(
    tmp_path: Path,
) -> None:
    payload = DashboardStrategyService(
        tmp_path / "missing.db",
        now_provider=lambda: NOW,
    ).create_payload(
        trading_date=NOW.date()
    )

    assert len(payload.strategies) == 3
    assert payload.recent_trades == ()
