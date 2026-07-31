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



def test_service_loads_recent_completed_trades(
    tmp_path: Path,
) -> None:
    path = create_database(tmp_path)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE trade_journal (
                id INTEGER PRIMARY KEY,
                trade_id TEXT,
                strategy_name TEXT,
                code TEXT,
                entry_at TEXT,
                exit_at TEXT,
                entry_price REAL,
                exit_price REAL,
                quantity INTEGER,
                realized_profit_loss REAL,
                return_rate REAL,
                holding_minutes REAL,
                exit_reason TEXT,
                maximum_favorable_excursion_rate REAL,
                maximum_adverse_excursion_rate REAL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO trade_journal
            VALUES (
                1,
                'journal-001',
                'opening-range-breakout-v2',
                '7203',
                '2026-08-03T09:30:00+00:00',
                '2026-08-03T10:00:00+00:00',
                1000,
                1020,
                100,
                1800,
                0.018,
                30,
                'take_profit',
                0.025,
                -0.005
            )
            """
        )
        connection.commit()

    payload = DashboardStrategyService(
        path,
        now_provider=lambda: NOW,
    ).create_payload(
        trading_date=NOW.date()
    )

    assert len(
        payload.recent_completed_trades
    ) == 1
    assert payload.recent_completed_trades[0][
        "strategy_name"
    ] == "ORB"
