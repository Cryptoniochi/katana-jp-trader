from dataclasses import dataclass
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.live.live_execution_tracking_flow import LivePositionBaselineConflictError
from app.live.live_protective_exit_execution_flow import (
    LiveProtectiveExitExecutionDecision,
    LiveProtectiveExitExecutionFlow,
)
from app.live.live_protective_exit_service import LiveProtectiveExitService
from app.trading.order_models import OrderSide, OrderType, TradeOrder

NOW=datetime(2026,10,13,6,30,tzinfo=timezone.utc)
DAY=date(2026,10,13)

@dataclass(frozen=True)
class Position:
    code: str
    quantity: int

@dataclass(frozen=True)
class State:
    positions: tuple[Position,...]

class RefreshAccount:
    def __init__(self, positions): self.positions=positions; self.calls=0
    def refresh(self): self.calls+=1; return State(self.positions)

class Tracking:
    def __init__(self, baseline_quantity=None, fail=False):
        self.baseline_quantity=baseline_quantity; self.fail=fail
        self.submissions=[]; self.reconciliations=[]
    def submit(self, **kwargs):
        self.submissions.append(kwargs)
        required=kwargs["required_baseline_quantity"]
        if self.fail or (self.baseline_quantity is not None and self.baseline_quantity != required):
            raise LivePositionBaselineConflictError("position changed")
        return SimpleNamespace(decision="submitted")
    def reconcile(self, **kwargs):
        self.reconciliations.append(kwargs)
        return SimpleNamespace(decision="filled_consistent")

def make_flow(positions, price=100.0, tracking=None):
    account=RefreshAccount(tuple(Position(*x) for x in positions))
    service=LiveProtectiveExitService(
        account_state_provider=account,
        market_price_provider=lambda code: price,
        now_provider=lambda: NOW,
    )
    tracking=tracking or Tracking()
    return LiveProtectiveExitExecutionFlow(
        exit_service=service, tracking_flow=tracking
    ), account, tracking

def test_real_refresh_contract_is_used_for_stop_planning():
    flow, account, tracking=make_flow(
        [("3911",100)],190,Tracking(baseline_quantity=100)
    )
    result=flow.submit_stop_loss(code="3911",stop_price=200,trading_date=DAY)
    assert account.calls == 1
    assert result.decision is LiveProtectiveExitExecutionDecision.SUBMISSION_STARTED
    sent=tracking.submissions[0]
    assert sent["order"].side is OrderSide.SELL
    assert sent["order"].order_type is OrderType.MARKET
    assert sent["required_baseline_quantity"] == 100

def test_stop_not_hit_never_reaches_tracking():
    flow,_,tracking=make_flow([("3911",100)],201)
    result=flow.submit_stop_loss(code="3911",stop_price=200,trading_date=DAY)
    assert result.decision is LiveProtectiveExitExecutionDecision.NO_ACTION
    assert tracking.submissions == []

def test_missing_position_never_reaches_tracking():
    flow,_,tracking=make_flow([],190)
    result=flow.submit_stop_loss(code="3911",stop_price=200,trading_date=DAY)
    assert result.decision is LiveProtectiveExitExecutionDecision.NO_ACTION
    assert tracking.submissions == []

def test_position_change_between_plan_and_submission_blocks():
    flow,_,_=make_flow([("3911",100)],190,Tracking(baseline_quantity=80))
    result=flow.submit_stop_loss(code="3911",stop_price=200,trading_date=DAY)
    assert result.decision is LiveProtectiveExitExecutionDecision.BLOCKED
    assert result.may_retry_same_order is False

def test_end_of_day_submits_every_real_position():
    flow,_,tracking=make_flow([("3911",100),("7203",200)],tracking=Tracking())
    batch=flow.submit_end_of_day(trading_date=DAY)
    assert batch.is_blocked is False
    assert [x["order"].code for x in tracking.submissions] == ["3911","7203"]
    assert [x["required_baseline_quantity"] for x in tracking.submissions] == [100,200]

def test_end_of_day_stops_after_first_guard_failure():
    flow,_,tracking=make_flow(
        [("3911",100),("7203",200)],tracking=Tracking(fail=True)
    )
    batch=flow.submit_end_of_day(trading_date=DAY)
    assert batch.is_blocked is True
    assert len(tracking.submissions) == 1

def test_reconcile_delegates_sell_to_tracking():
    flow,_,tracking=make_flow([])
    order=TradeOrder(
        order_id="o1",signal_id="s1",code="3911",side=OrderSide.SELL,
        order_type=OrderType.MARKET,quantity=100
    )
    result=flow.reconcile(execution_key="e1",order=order)
    assert result.decision == "filled_consistent"
    assert tracking.reconciliations == [{"execution_key":"e1","order":order}]

def test_reconcile_rejects_buy():
    flow,_,_=make_flow([])
    order=TradeOrder(
        order_id="o1",signal_id="s1",code="3911",side=OrderSide.BUY,
        order_type=OrderType.MARKET,quantity=100
    )
    with pytest.raises(ValueError):
        flow.reconcile(execution_key="e1",order=order)

def test_same_order_is_never_retryable():
    flow,_,_=make_flow([("3911",100)],190,Tracking(fail=True))
    result=flow.submit_stop_loss(code="3911",stop_price=200,trading_date=DAY)
    assert result.may_retry_same_order is False
