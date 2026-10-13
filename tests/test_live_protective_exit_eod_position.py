from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.live.live_protective_exit_service import (
    LiveProtectiveExitDecision,
    LiveProtectiveExitService,
)

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
    def __init__(self, quantity):
        self.quantity=quantity
    def refresh(self):
        return State(()) if self.quantity==0 else State((Position("3911",self.quantity),))

def service(quantity):
    return LiveProtectiveExitService(
        account_state_provider=Account(quantity),
        market_price_provider=lambda _code:190,
        now_provider=lambda:NOW,
    )

def test_evaluate_eod_position_uses_fresh_actual_quantity():
    plan=service(40).evaluate_eod_position(code="3911",trading_date=DAY)
    assert plan.decision is LiveProtectiveExitDecision.EXIT_REQUIRED
    assert plan.quantity==40
    assert plan.order is not None
    assert plan.order.quantity==40

def test_evaluate_eod_position_zero_is_no_position():
    plan=service(0).evaluate_eod_position(code="3911",trading_date=DAY)
    assert plan.decision is LiveProtectiveExitDecision.NO_POSITION
    assert plan.quantity==0
    assert plan.order is None
