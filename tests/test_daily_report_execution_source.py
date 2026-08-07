"""Daily Reportが実約定を正本として集計することを確認する。"""

import sqlite3
from datetime import date
from pathlib import Path

from app.runtime.daily_report_service import (
    DailyReportService,
    SQLiteDailyTradeRepository,
)


REPORT_DATE = date(2026, 8, 7)


def _create_execution_schema(
    database: Path,
) -> None:
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE trade_signals (
                signal_id TEXT PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                action TEXT NOT NULL
            );

            CREATE TABLE trade_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT NOT NULL UNIQUE,
                signal_id TEXT NOT NULL,
                code TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                execution_price REAL NOT NULL,
                executed_at TEXT NOT NULL,
                commission REAL NOT NULL DEFAULT 0,
                slippage REAL NOT NULL DEFAULT 0
            );

            CREATE TABLE trade_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exit_at TEXT NOT NULL,
                code TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                realized_profit_loss REAL NOT NULL
            );
            """
        )
        connection.commit()


def _signal(
    connection,
    signal_id: str,
    strategy: str,
    action: str,
) -> None:
    connection.execute(
        """
        INSERT INTO trade_signals (
            signal_id,
            strategy_name,
            action
        ) VALUES (?, ?, ?)
        """,
        (
            signal_id,
            strategy,
            action,
        ),
    )


def _execution(
    connection,
    *,
    execution_id: str,
    signal_id: str,
    code: str,
    side: str,
    quantity: int,
    price: float,
    executed_at: str,
) -> None:
    connection.execute(
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
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)
        """,
        (
            execution_id,
            signal_id,
            code,
            side,
            quantity,
            price,
            executed_at,
        ),
    )


def test_execution_fifo_is_used_when_trade_journal_is_empty(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    _create_execution_schema(database)

    with sqlite3.connect(database) as connection:
        _signal(
            connection,
            "buy-1",
            "opening-range-breakout-v2",
            "buy",
        )
        _signal(
            connection,
            "sell-1",
            "opening-range-breakout-v2",
            "exit",
        )
        _execution(
            connection,
            execution_id="exec-buy-1",
            signal_id="buy-1",
            code="7203",
            side="buy",
            quantity=100,
            price=3000.0,
            executed_at="2026-08-07T00:30:00+00:00",
        )
        _execution(
            connection,
            execution_id="exec-sell-1",
            signal_id="sell-1",
            code="7203",
            side="sell",
            quantity=100,
            price=2946.0,
            executed_at="2026-08-07T06:00:00+00:00",
        )
        connection.commit()

    repository = SQLiteDailyTradeRepository(
        database
    )
    records = repository.list_closed_trades(
        REPORT_DATE
    )

    assert len(records) == 1
    assert records[0].symbol == "7203"
    assert records[0].realized_profit_loss == -5400.0

    report = DailyReportService(
        repository
    ).generate(
        report_date=REPORT_DATE
    )

    assert report.summary.trade_count == 1
    assert report.summary.net_profit_loss == -5400.0
    assert report.summary.loss_count == 1
    assert report.summary.win_rate == 0.0


def test_execution_source_wins_over_stale_trade_journal(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    _create_execution_schema(database)

    with sqlite3.connect(database) as connection:
        # stale/incorrect journal entry: old implementation would read this.
        connection.execute(
            """
            INSERT INTO trade_journal (
                exit_at,
                code,
                strategy_name,
                realized_profit_loss
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "2026-08-07T06:00:00+00:00",
                "7203",
                "opening-range-breakout-v2",
                0.0,
            ),
        )
        _signal(
            connection,
            "buy-1",
            "pullback-breakout-v1",
            "buy",
        )
        _signal(
            connection,
            "sell-1",
            "pullback-breakout-v1",
            "sell",
        )
        _execution(
            connection,
            execution_id="exec-buy-1",
            signal_id="buy-1",
            code="8306",
            side="buy",
            quantity=100,
            price=3600.0,
            executed_at="2026-08-07T01:00:00+00:00",
        )
        _execution(
            connection,
            execution_id="exec-sell-1",
            signal_id="sell-1",
            code="8306",
            side="sell",
            quantity=100,
            price=3575.0,
            executed_at="2026-08-07T02:00:00+00:00",
        )
        connection.commit()

    records = SQLiteDailyTradeRepository(
        database
    ).list_closed_trades(
        REPORT_DATE
    )

    assert len(records) == 1
    assert records[0].symbol == "8306"
    assert records[0].realized_profit_loss == -2500.0


def test_legacy_trade_journal_still_works_without_execution_tables(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE trade_journal (
                closed_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                realized_profit_loss REAL NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO trade_journal (
                closed_at,
                symbol,
                strategy_name,
                realized_profit_loss
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "2026-08-07T06:00:00+00:00",
                "6758",
                "orb",
                1200.0,
            ),
        )
        connection.commit()

    records = SQLiteDailyTradeRepository(
        database
    ).list_closed_trades(
        REPORT_DATE
    )

    assert len(records) == 1
    assert records[0].symbol == "6758"
    assert records[0].realized_profit_loss == 1200.0
