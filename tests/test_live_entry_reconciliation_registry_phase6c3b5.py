from datetime import date
from app.live.live_entry_reconciliation_registry import (
    LiveEntryReconciliationState, SQLiteLiveEntryReconciliationRegistry)
from app.trading.order_models import OrderSide,OrderType,TradeOrder
DAY=date(2026,10,14)
def order():
    return TradeOrder(order_id="o",signal_id="s",code="7203",side=OrderSide.BUY,
                      order_type=OrderType.MARKET,quantity=100)
def test_registry_survives_restart_and_completes(tmp_path):
    p=tmp_path/"k.db"; r=SQLiteLiveEntryReconciliationRegistry(p)
    r.prepare(execution_key="e",trading_date=DAY,order=order())
    reopened=SQLiteLiveEntryReconciliationRegistry(p)
    assert reopened.list_pending()[0].to_order()==order()
    reopened.complete("e")
    assert reopened.list_pending()==()
    assert reopened.get_required("e").state is LiveEntryReconciliationState.COMPLETE
