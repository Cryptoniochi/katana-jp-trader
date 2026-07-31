"""TradeJournalRepositoryのテスト。"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.database import (
    SCHEMA_VERSION,
    initialize_database,
)
from app.trading.trade_journal_models import (
    TradeJournalEntry,
)
from app.trading.trade_journal_repository import (
    TradeJournalRepository,
)


NOW = datetime(
    2026,
    8,
    3,
    1,
    0,
    tzinfo=timezone.utc,
)


def insert_dependencies(
    database_path: Path,
) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO trade_signals (
                signal_id, code, strategy_name, action,
                generated_at, signal_price, quantity,
                reason, metadata_json, status
            )
            VALUES (
                'entry-signal', '7203', 'orb', 'buy',
                ?, 1000, 100, 'entry', '{}', 'processed'
            )
            """,
            (NOW.isoformat(),),
        )
        connection.execute(
            """
            INSERT INTO trade_signals (
                signal_id, code, strategy_name, action,
                generated_at, signal_price, quantity,
                reason, metadata_json, status
            )
            VALUES (
                'exit-signal', '7203', 'orb', 'exit',
                ?, 1020, 100, 'take_profit',
                '{"exit_reason":"take_profit"}',
                'processed'
            )
            """,
            (NOW.isoformat(),),
        )
        connection.execute(
            """
            INSERT INTO trade_orders (
                order_id, signal_id, code, side,
                order_type, quantity, status,
                filled_quantity, created_at, updated_at
            )
            VALUES (
                'entry-order', 'entry-signal', '7203', 'buy',
                'market', 100, 'filled', 100, ?, ?
            )
            """,
            (NOW.isoformat(), NOW.isoformat()),
        )
        connection.execute(
            """
            INSERT INTO trade_orders (
                order_id, signal_id, code, side,
                order_type, quantity, status,
                filled_quantity, created_at, updated_at
            )
            VALUES (
                'exit-order', 'exit-signal', '7203', 'sell',
                'market', 100, 'filled', 100, ?, ?
            )
            """,
            (NOW.isoformat(), NOW.isoformat()),
        )
        for execution_id, signal_id, order_id, side, price in (
            (
                "entry-execution",
                "entry-signal",
                "entry-order",
                "buy",
                1000.0,
            ),
            (
                "exit-execution",
                "exit-signal",
                "exit-order",
                "sell",
                1020.0,
            ),
        ):
            connection.execute(
                """
                INSERT INTO trade_executions (
                    execution_id, signal_id, order_id,
                    broker_order_id, code, side, quantity,
                    execution_price, executed_at, broker_name,
                    commission, slippage, metadata_json,
                    created_at, updated_at
                )
                VALUES (
                    ?, ?, ?, ?, '7203', ?, 100,
                    ?, ?, 'paper', 0, 0, '{}', ?, ?
                )
                """,
                (
                    execution_id,
                    signal_id,
                    order_id,
                    f"broker-{order_id}",
                    side,
                    price,
                    NOW.isoformat(),
                    NOW.isoformat(),
                    NOW.isoformat(),
                ),
            )
        connection.commit()


def make_entry() -> TradeJournalEntry:
    return TradeJournalEntry(
        trade_id="journal-001",
        strategy_name="orb",
        code="7203",
        entry_signal_id="entry-signal",
        exit_signal_id="exit-signal",
        entry_execution_id="entry-execution",
        exit_execution_id="exit-execution",
        entry_at=NOW,
        exit_at=NOW,
        entry_price=1000.0,
        exit_price=1020.0,
        quantity=100,
        entry_cost=100.0,
        exit_cost=100.0,
        realized_profit_loss=1800.0,
        return_rate=0.018,
        holding_minutes=0.0,
        exit_reason="take_profit",
        maximum_favorable_excursion=2500.0,
        maximum_adverse_excursion=-500.0,
        maximum_favorable_excursion_rate=0.025,
        maximum_adverse_excursion_rate=-0.005,
    )


def test_database_creates_trade_journal(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'trade_journal'
            """
        ).fetchone()

    assert table == ("trade_journal",)
    assert SCHEMA_VERSION == 14


def test_repository_saves_reads_and_upserts(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "katana.db"
    initialize_database(database_path)
    insert_dependencies(database_path)

    repository = TradeJournalRepository(
        database_path,
        now_provider=lambda: NOW,
    )
    saved = repository.save(make_entry())

    assert saved.entry.trade_id == "journal-001"
    assert repository.get(
        "journal-001"
    ) == saved
    assert repository.count() == 1

    from dataclasses import replace

    updated = replace(
        make_entry(),
        realized_profit_loss=1700.0,
    )
    repository.save(updated)

    assert repository.count() == 1
    assert repository.get(
        "journal-001"
    ).entry.realized_profit_loss == 1700.0
    assert len(repository.list_recent()) == 1
