from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.live.live_exit_order_conflict_service import LiveExitOrderConflictService
from app.live.live_protective_cancel_service import LiveProtectiveCancelService
from app.live.live_protective_exit_conflict_resolver import LiveProtectiveExitConflictResolver
from app.live.live_protective_exit_execution_flow import (
    LiveProtectiveExitExecutionDecision,
    LiveProtectiveExitExecutionFlow,
)
from app.live.live_protective_exit_service import LiveProtectiveExitService

DAY=date(2026,10,13)
NOW=datetime(2026,10,13,6,30,tzinfo=timezone.utc)

@dataclass(frozen=True)
class P:
    code:str="3911"
    quantity:int=100

@dataclass(frozen=True)
class S:
    positions:tuple=(P(),)

class Account:
    def refresh(self): return S()

class Orders:
    def __init__(self,rows): self.rows=list(rows); self.cancel_calls=0
    def orders(self,*,product=0): return tuple(self.rows)
    def cancel_order(self,oid):
        self.cancel_calls+=1
        # This legacy boundary test deliberately keeps the conflict active,
        # proving tracking cannot start until broker state becomes terminal.
        return {"Result":0,"OrderId":oid}

class Tracking:
    def __init__(self): self.calls=[]
    def submit(self,**kwargs): self.calls.append(kwargs); return object()

def build(rows):
    broker=Orders(rows)
    tracking=Tracking()
    service=LiveProtectiveExitService(
        account_state_provider=Account(),
        market_price_provider=lambda c:190,
        now_provider=lambda:NOW,
    )
    resolver=LiveProtectiveExitConflictResolver(
        conflict_service=LiveExitOrderConflictService(order_reader=broker),
        cancel_service=LiveProtectiveCancelService(client=broker),
        exit_service=service,
    )
    flow=LiveProtectiveExitExecutionFlow(
        exit_service=service,
        tracking_flow=tracking,
        conflict_resolver=resolver,
    )
    return flow,tracking,broker

def test_active_sell_blocks_before_tracking():
    f,t,b=build([{"ID":"s","Symbol":"3911","Side":"1","State":3,"LeavesQty":100}])
    r=f.submit_stop_loss(code="3911",stop_price=200,trading_date=DAY)
    assert r.decision is LiveProtectiveExitExecutionDecision.BLOCKED
    assert t.calls==[]
    assert b.cancel_calls==1

def test_active_buy_blocks_before_tracking():
    f,t,b=build([{"ID":"b","Symbol":"3911","Side":"2","State":2,"LeavesQty":100}])
    r=f.submit_stop_loss(code="3911",stop_price=200,trading_date=DAY)
    assert r.decision is LiveProtectiveExitExecutionDecision.BLOCKED
    assert t.calls==[]
    assert b.cancel_calls==1

def test_terminal_order_allows_tracking():
    f,t,b=build([{"ID":"d","Symbol":"3911","Side":"1","State":5,"LeavesQty":0}])
    r=f.submit_stop_loss(code="3911",stop_price=200,trading_date=DAY)
    assert r.decision is LiveProtectiveExitExecutionDecision.SUBMISSION_STARTED
    assert len(t.calls)==1
    assert b.cancel_calls==0
