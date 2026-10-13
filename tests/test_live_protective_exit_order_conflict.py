from datetime import date,datetime,timezone
from dataclasses import dataclass
from types import SimpleNamespace
from app.live.live_exit_order_conflict_service import LiveExitOrderConflictService
from app.live.live_protective_exit_execution_flow import LiveProtectiveExitExecutionDecision,LiveProtectiveExitExecutionFlow
from app.live.live_protective_exit_service import LiveProtectiveExitService
DAY=date(2026,10,13); NOW=datetime(2026,10,13,6,30,tzinfo=timezone.utc)
@dataclass(frozen=True)
class P: code:str; quantity:int
@dataclass(frozen=True)
class S: positions:tuple[P,...]
class Account:
    def refresh(self): return S((P("3911",100),))
class Orders:
    def __init__(self,rows): self.rows=rows
    def orders(self,*,product=0): return tuple(self.rows)
class Tracking:
    def __init__(self): self.calls=0
    def submit(self,**kwargs): self.calls+=1; return SimpleNamespace(decision="submitted")
    def reconcile(self,**kwargs): return SimpleNamespace()
def build(rows):
    tracking=Tracking()
    flow=LiveProtectiveExitExecutionFlow(
      exit_service=LiveProtectiveExitService(account_state_provider=Account(),market_price_provider=lambda c:190,now_provider=lambda:NOW),
      tracking_flow=tracking,
      order_conflict_service=LiveExitOrderConflictService(order_reader=Orders(rows)))
    return flow,tracking
def test_active_sell_blocks_before_tracking():
    f,t=build([{"ID":"s","Symbol":"3911","Side":"1","State":3,"LeavesQty":100}])
    assert f.submit_stop_loss(code="3911",stop_price=200,trading_date=DAY).decision is LiveProtectiveExitExecutionDecision.BLOCKED
    assert t.calls==0
def test_active_buy_blocks_before_tracking():
    f,t=build([{"ID":"b","Symbol":"3911","Side":"2","State":2,"LeavesQty":100}])
    assert f.submit_stop_loss(code="3911",stop_price=200,trading_date=DAY).decision is LiveProtectiveExitExecutionDecision.BLOCKED
    assert t.calls==0
def test_terminal_order_allows_tracking():
    f,t=build([{"ID":"d","Symbol":"3911","Side":"1","State":5,"LeavesQty":0}])
    assert f.submit_stop_loss(code="3911",stop_price=200,trading_date=DAY).decision is LiveProtectiveExitExecutionDecision.SUBMISSION_STARTED
    assert t.calls==1
