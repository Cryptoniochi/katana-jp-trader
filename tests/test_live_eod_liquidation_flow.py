from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.live.live_eod_liquidation_flow import (
    LiveEodExecutionDecision,
    LiveEodLiquidationFlow,
)
from app.live.live_exit_order_conflict_service import LiveExitOrderConflictService
from app.live.live_cancel_journal_repository import SQLiteLiveCancelJournalRepository
from app.live.live_protective_cancel_service import LiveProtectiveCancelService
from app.live.live_protective_exit_conflict_resolver import LiveProtectiveExitConflictResolver
from app.live.live_protective_exit_execution_flow import LiveProtectiveExitExecutionFlow
from app.live.live_protective_exit_service import LiveProtectiveExitService

DAY=date(2026,10,13)
NOW=datetime(2026,10,13,6,30,tzinfo=timezone.utc)

@dataclass(frozen=True)
class Position:
    code:str
    quantity:int

@dataclass(frozen=True)
class State:
    positions:tuple[Position,...]

class Account:
    def __init__(self, positions):
        self.positions=positions
    def refresh(self):
        return State(tuple(Position(c,q) for c,q in self.positions.items() if q))

class Broker:
    def __init__(self, rows=()):
        self.rows=list(rows)
        self.cancel_calls=[]
    def orders(self,*,product=0):
        return tuple(self.rows)
    def cancel_order(self,oid):
        self.cancel_calls.append(oid)
        for row in self.rows:
            if row["ID"]==oid:
                row["State"]=5
                row["LeavesQty"]=0
        return {"Result":0,"OrderId":oid}

class Tracking:
    def __init__(self):
        self.calls=[]
    def submit(self,**kwargs):
        self.calls.append(kwargs)
        return object()

def build(tmp_path, account, broker):
    service=LiveProtectiveExitService(
        account_state_provider=account,
        market_price_provider=lambda code:190,
        now_provider=lambda:NOW,
    )
    resolver=LiveProtectiveExitConflictResolver(
        conflict_service=LiveExitOrderConflictService(order_reader=broker),
        cancel_service=LiveProtectiveCancelService(
            client=broker,
            journal_repository=SQLiteLiveCancelJournalRepository(tmp_path/"katana.db"),
        ),
        exit_service=service,
    )
    tracking=Tracking()
    execution=LiveProtectiveExitExecutionFlow(
        exit_service=service,
        tracking_flow=tracking,
        conflict_resolver=resolver,
    )
    return LiveEodLiquidationFlow(
        exit_service=service,
        conflict_resolver=resolver,
        execution_flow=execution,
    ),tracking

def test_eod_no_conflict_uses_actual_position_quantity(tmp_path):
    flow,tracking=build(tmp_path,Account({"3911":70}),Broker())
    result=flow.submit_all(trading_date=DAY)
    assert result.decision is LiveEodExecutionDecision.COMPLETE
    assert len(tracking.calls)==1
    assert tracking.calls[0]["order"].code=="3911"
    assert tracking.calls[0]["order"].quantity==70
    assert tracking.calls[0]["required_baseline_quantity"]==70

def test_eod_active_order_is_cancelled_before_submission(tmp_path):
    broker=Broker([{"ID":"OID","Symbol":"3911","Side":"2","State":3,"LeavesQty":100}])
    flow,tracking=build(tmp_path,Account({"3911":40}),broker)
    result=flow.submit_all(trading_date=DAY)
    assert result.decision is LiveEodExecutionDecision.COMPLETE
    assert broker.cancel_calls==["OID"]
    assert len(tracking.calls)==1
    assert tracking.calls[0]["order"].quantity==40

def test_eod_ambiguous_cancel_blocks_submission(tmp_path):
    class BadBroker(Broker):
        def cancel_order(self,oid):
            self.cancel_calls.append(oid)
            raise RuntimeError("timeout")
    broker=BadBroker([{"ID":"OID","Symbol":"3911","Side":"1","State":3,"LeavesQty":100}])
    flow,tracking=build(tmp_path,Account({"3911":100}),broker)
    result=flow.submit_all(trading_date=DAY)
    assert result.decision is LiveEodExecutionDecision.BLOCKED
    assert tracking.calls==[]
    assert broker.cancel_calls==["OID"]

def test_eod_multiple_symbols_are_each_replanned(tmp_path):
    flow,tracking=build(tmp_path,Account({"3911":30,"7203":20}),Broker())
    result=flow.submit_all(trading_date=DAY)
    assert result.decision is LiveEodExecutionDecision.COMPLETE
    assert [(c["order"].code,c["order"].quantity) for c in tracking.calls]==[
        ("3911",30),("7203",20)
    ]
