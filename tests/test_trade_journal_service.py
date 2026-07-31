"""TradeJournalServiceのテスト。"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.database import initialize_database
from app.trading.trade_journal_repository import (
    TradeJournalRepository,
)
from app.trading.trade_journal_service import (
    TradeJournalService,
)


ENTRY_AT = datetime(
    2026,
    8,
    3,
    0,
    30,
    tzinfo=timezone.utc,
)
EXIT_AT = ENTRY_AT + timedelta(minutes=30)


def prepare_database(
    tmp_path: Path,
) -> Path:
    path = tmp_path / "katana.db"
    initialize_database(path)

    with sqlite3.connect(path) as connection:
        for signal_id, action, price, reason, metadata in (
            (
                "entry-signal",
                "buy",
                1000.0,
                "breakout",
                "{}",
            ),
            (
                "exit-signal",
                "exit",
                1020.0,
                "high breakout exit: take_profit",
                '{"exit_reason":"take_profit"}',
            ),
        ):
            generated_at = (
                ENTRY_AT
                if action == "buy"
                else EXIT_AT
            )
            connection.execute(
                """
                INSERT INTO trade_signals (
                    signal_id, code, strategy_name,
                    action, generated_at, signal_price,
                    quantity, reason, metadata_json, status
                )
                VALUES (
                    ?, '7203', 'high-breakout-v1',
                    ?, ?, ?, 100, ?, ?, 'processed'
                )
                """,
                (
                    signal_id,
                    action,
                    generated_at.isoformat(),
                    price,
                    reason,
                    metadata,
                ),
            )

        for order_id, signal_id, side, created_at in (
            (
                "entry-order",
                "entry-signal",
                "buy",
                ENTRY_AT,
            ),
            (
                "exit-order",
                "exit-signal",
                "sell",
                EXIT_AT,
            ),
        ):
            connection.execute(
                """
                INSERT INTO trade_orders (
                    order_id, signal_id, code, side,
                    order_type, quantity, status,
                    filled_quantity, created_at, updated_at
                )
                VALUES (
                    ?, ?, '7203', ?, 'market',
                    100, 'filled', 100, ?, ?
                )
                """,
                (
                    order_id,
                    signal_id,
                    side,
                    created_at.isoformat(),
                    created_at.isoformat(),
                ),
            )

        for execution_id, signal_id, order_id, side, price, executed_at in (
            (
                "entry-execution",
                "entry-signal",
                "entry-order",
                "buy",
                1000.0,
                ENTRY_AT,
            ),
            (
                "exit-execution",
                "exit-signal",
                "exit-order",
                "sell",
                1020.0,
                EXIT_AT,
            ),
        ):
            connection.execute(
                """
                INSERT INTO trade_executions (
                    execution_id, signal_id, order_id,
                    broker_order_id, code, side,
                    quantity, execution_price, executed_at,
                    broker_name, commission, slippage,
                    metadata_json, created_at, updated_at
                )
                VALUES (
                    ?, ?, ?, ?, '7203', ?, 100,
                    ?, ?, 'paper', 100, 0, '{}', ?, ?
                )
                """,
                (
                    execution_id,
                    signal_id,
                    order_id,
                    f"broker-{order_id}",
                    side,
                    price,
                    executed_at.isoformat(),
                    executed_at.isoformat(),
                    executed_at.isoformat(),
                ),
            )

        bars = (
            (
                ENTRY_AT,
                1005.0,
                995.0,
            ),
            (
                ENTRY_AT + timedelta(minutes=5),
                1030.0,
                990.0,
            ),
            (
                EXIT_AT,
                1025.0,
                1010.0,
            ),
        )
        for traded_at, high, low in bars:
            connection.execute(
                """
                INSERT INTO market_bars (
                    code, traded_at, interval_minutes,
                    open, high, low, close,
                    volume, data_source
                )
                VALUES (
                    '7203', ?, 5,
                    1000, ?, ?, 1010,
                    1000, 'test'
                )
                """,
                (
                    traded_at.isoformat(),
                    high,
                    low,
                ),
            )

        connection.commit()

    return path


def test_service_rebuilds_completed_trade(
    tmp_path: Path,
) -> None:
    path = prepare_database(tmp_path)
    entries = TradeJournalService(
        path
    ).rebuild()

    assert len(entries) == 1
    entry = entries[0]

    assert entry.strategy_name == (
        "high-breakout-v1"
    )
    assert entry.quantity == 100
    assert entry.realized_profit_loss == pytest.approx(
        1800.0
    )
    assert entry.return_rate == pytest.approx(
        0.018
    )
    assert entry.holding_minutes == pytest.approx(
        30.0
    )
    assert entry.exit_reason == "take_profit"
    assert entry.maximum_favorable_excursion == pytest.approx(
        3000.0
    )
    assert entry.maximum_adverse_excursion == pytest.approx(
        -1000.0
    )
    assert TradeJournalRepository(path).count() == 1


def test_service_is_idempotent(
    tmp_path: Path,
) -> None:
    path = prepare_database(tmp_path)
    service = TradeJournalService(path)

    service.rebuild()
    service.rebuild()

    assert TradeJournalRepository(path).count() == 1
