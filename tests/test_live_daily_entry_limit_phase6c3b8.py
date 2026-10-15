from datetime import date
from pathlib import Path
import pytest

from app.live.live_entry_reconciliation_registry import (
    LiveDailyEntryLimitError,
    SQLiteLiveEntryReconciliationRegistry,
)
from app.trading.order_models import OrderSide, OrderType, TradeOrder


def _order(n: int) -> TradeOrder:
    return TradeOrder(
        order_id=f"o-{n}", signal_id=f"s-{n}", code=f"{1000+n}",
        side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100,
    )


def test_daily_live_entry_limit_is_durable_and_idempotent(tmp_path: Path):
    db=tmp_path/"katana.db"
    day=date(2026,10,16)
    registry=SQLiteLiveEntryReconciliationRegistry(db,max_entries_per_day=2)
    registry.prepare(execution_key="k1",trading_date=day,order=_order(1))
    registry.prepare(execution_key="k2",trading_date=day,order=_order(2))
    assert registry.count_for_date(day)==2

    # Replay of the same durable identity is allowed and does not consume a slot.
    registry.prepare(execution_key="k2",trading_date=day,order=_order(2))
    assert registry.count_for_date(day)==2

    # Restart preserves the cap.
    restarted=SQLiteLiveEntryReconciliationRegistry(db,max_entries_per_day=2)
    with pytest.raises(LiveDailyEntryLimitError):
        restarted.prepare(execution_key="k3",trading_date=day,order=_order(3))
    assert restarted.count_for_date(day)==2


def test_daily_limit_resets_by_trading_date(tmp_path: Path):
    registry=SQLiteLiveEntryReconciliationRegistry(
        tmp_path/"katana.db",max_entries_per_day=1
    )
    registry.prepare(
        execution_key="a",trading_date=date(2026,10,16),order=_order(1)
    )
    registry.prepare(
        execution_key="b",trading_date=date(2026,10,17),order=_order(2)
    )
