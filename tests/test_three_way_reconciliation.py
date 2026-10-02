"""Paper/Shadow/実口座在庫の三者照合テスト。"""

import json
import sqlite3
from datetime import date

from app.live.three_way_reconciliation import (
    BrokerInventoryReader,
    PaperExecutionReader,
    ReconciliationOrder,
    ShadowLedgerReader,
    ThreeWayReconciliationService,
)


TARGET_DATE = date(2026, 10, 2)


def order(order_id="order-1", *, quantity=100):
    return ReconciliationOrder(
        order_id=order_id,
        signal_id="signal-1",
        code="7203",
        side="buy",
        quantity=quantity,
    )


def reconcile(*, paper=(), shadow=(), connected=True, active=(), positions=()):
    return ThreeWayReconciliationService().reconcile(
        trading_date=TARGET_DATE,
        paper_orders=tuple(paper),
        shadow_orders=tuple(shadow),
        broker_snapshot_connected=connected,
        broker_active_order_ids=tuple(active),
        broker_position_codes=tuple(positions),
    )


def test_consistent_when_paper_shadow_match_and_broker_is_empty():
    report = reconcile(paper=(order(),), shadow=(order(),))

    assert report.consistent is True
    assert report.state == "consistent"
    assert report.matched_order_count == 1
    assert report.issue_count == 0
    assert report.live_order_ready is False


def test_quantity_mismatch_blocks_without_claiming_live_ready():
    report = reconcile(
        paper=(order(quantity=100),),
        shadow=(order(quantity=200),),
    )

    assert report.consistent is False
    assert len(report.mismatches) == 1
    assert report.issue_count == 1
    assert report.live_order_ready is False


def test_broker_inventory_blocks_even_when_paper_shadow_match():
    report = reconcile(
        paper=(order(),),
        shadow=(order(),),
        active=("broker-1",),
        positions=("7203",),
    )

    assert report.consistent is False
    assert report.broker_active_order_count == 1
    assert report.broker_position_count == 1
    assert report.issue_count == 2


def test_paper_reader_aggregates_partial_fills_for_tokyo_date(tmp_path):
    database = tmp_path / "katana.db"
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE trade_executions (
            id INTEGER PRIMARY KEY,
            order_id TEXT,
            signal_id TEXT,
            code TEXT,
            side TEXT,
            quantity INTEGER,
            executed_at TEXT
        )
        """
    )
    connection.executemany(
        """
        INSERT INTO trade_executions
            (order_id, signal_id, code, side, quantity, executed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("order-1", "signal-1", "7203", "buy", 40,
             "2026-10-02T00:30:00+00:00"),
            ("order-1", "signal-1", "7203", "buy", 60,
             "2026-10-02T00:31:00+00:00"),
            ("old", "old-signal", "6503", "buy", 100,
             "2026-10-01T00:30:00+00:00"),
        ],
    )
    connection.commit()
    connection.close()

    result = PaperExecutionReader(database).read(TARGET_DATE)

    assert result == (order(quantity=100),)


def test_shadow_reader_filters_submitted_events_by_tokyo_date(tmp_path):
    ledger = tmp_path / "shadow.jsonl"
    ledger.write_text(
        json.dumps({
            "event": "submitted",
            "recorded_at": "2026-10-02T00:30:00+00:00",
            "order": {
                "order_id": "order-1",
                "signal_id": "signal-1",
                "code": "7203",
                "side": "buy",
                "quantity": 100,
            },
        }) + "\n" + json.dumps({
            "event": "cancelled",
            "recorded_at": "2026-10-02T00:31:00+00:00",
        }) + "\n",
        encoding="utf-8",
    )

    assert ShadowLedgerReader(ledger).read(TARGET_DATE) == (order(),)


def test_broker_reader_only_treats_states_one_to_four_as_active(tmp_path):
    report = tmp_path / "broker.json"
    report.write_text(
        json.dumps({
            "connected": True,
            "orders": [
                {"ID": "active", "State": 3},
                {"ID": "done", "State": 5},
            ],
            "positions": [{"Symbol": "7203"}],
        }),
        encoding="utf-8",
    )

    connected, active, positions = BrokerInventoryReader(report).read()

    assert connected is True
    assert active == ("active",)
    assert positions == ("7203",)
