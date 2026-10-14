from datetime import date
from types import SimpleNamespace

from app.live.live_position_protection_reconciliation import (
    LivePositionProtectionReconciliation,
)
from app.live.live_protective_exit_service import (
    LiveEndOfDayExitBatch,
    LiveProtectiveExitDecision,
    LiveProtectiveExitPlan,
    LiveProtectiveExitReason,
)
from app.live.live_protective_stop_repository import SQLiteLiveProtectiveStopRepository
from app.trading.order_models import OrderSide, OrderType, TradeOrder
from datetime import datetime, timezone

DAY=date(2026,10,14)
NOW=datetime(2026,10,14,0,0,tzinfo=timezone.utc)

def plan(code, qty):
    order=TradeOrder(order_id="o-"+code,signal_id="s-"+code,code=code,
                     side=OrderSide.SELL,order_type=OrderType.MARKET,quantity=qty)
    return LiveProtectiveExitPlan(
        decision=LiveProtectiveExitDecision.EXIT_REQUIRED,
        reason=LiveProtectiveExitReason.END_OF_DAY,evaluated_at=NOW,
        code=code,quantity=qty,market_price=None,trigger_price=None,
        order=order,message="position")

class ExitService:
    def __init__(self, plans, blocked=False):
        self.plans=plans; self.blocked=blocked
    def plan_end_of_day(self, *, trading_date):
        if self.blocked:
            p=LiveProtectiveExitPlan(
                decision=LiveProtectiveExitDecision.BLOCKED,
                reason=LiveProtectiveExitReason.END_OF_DAY,evaluated_at=NOW,
                code=None,quantity=0,market_price=None,trigger_price=None,
                order=None,message="read failed")
            return LiveEndOfDayExitBatch(NOW,trading_date,(p,))
        return LiveEndOfDayExitBatch(NOW,trading_date,tuple(self.plans))

def repo(tmp_path):
    return SQLiteLiveProtectiveStopRepository(tmp_path/"katana.db")

def add(r, code="7203", qty=100, key="e1"):
    return r.record_filled_entry(code=code,entry_execution_key=key,
        trading_date=DAY,quantity=qty,fill_price=200.0)

def test_matching_position_and_stop_is_safe(tmp_path):
    r=repo(tmp_path); add(r)
    result=LivePositionProtectionReconciliation(
        repository=r,exit_service=ExitService([plan("7203",100)]))(DAY)
    assert result.blocked == 0
    assert result.retired_stale_stops == 0

def test_orphan_live_position_without_stop_blocks(tmp_path):
    r=repo(tmp_path)
    result=LivePositionProtectionReconciliation(
        repository=r,exit_service=ExitService([plan("7203",100)]))(DAY)
    assert result.blocked == 1

def test_quantity_mismatch_blocks(tmp_path):
    r=repo(tmp_path); add(r,qty=40)
    result=LivePositionProtectionReconciliation(
        repository=r,exit_service=ExitService([plan("7203",100)]))(DAY)
    assert result.blocked == 1

def test_stale_stop_is_retired_after_authoritative_flat(tmp_path):
    r=repo(tmp_path); add(r)
    result=LivePositionProtectionReconciliation(
        repository=r,exit_service=ExitService([]))(DAY)
    assert result.blocked == 0
    assert result.retired_stale_stops == 1
    assert r.list_current() == ()

def test_exit_pending_stop_is_retired_only_when_authoritative_flat(tmp_path):
    r=repo(tmp_path); add(r); r.mark_exit_pending(entry_execution_key="e1")
    result=LivePositionProtectionReconciliation(
        repository=r,exit_service=ExitService([]))(DAY)
    assert result.blocked == 0
    assert result.retired_stale_stops == 1

def test_account_read_failure_blocks_without_mutating_stop(tmp_path):
    r=repo(tmp_path); add(r)
    result=LivePositionProtectionReconciliation(
        repository=r,exit_service=ExitService([],blocked=True))(DAY)
    assert result.blocked == 1
    assert len(r.list_current()) == 1
