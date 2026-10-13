from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.live.live_exit_order_conflict_service import LiveExitOrderConflictService
from app.live.live_protective_cancel_service import LiveProtectiveCancelService
from app.live.live_protective_exit_conflict_resolver import (
    LiveConflictResolutionDecision,
    LiveProtectiveExitConflictResolver,
)
from app.live.live_protective_exit_service import (
    LiveProtectiveExitDecision,
    LiveProtectiveExitService,
)

DAY = date(2026, 10, 13)
NOW = datetime(2026, 10, 13, 6, 30, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Position:
    code: str
    quantity: int


@dataclass(frozen=True)
class State:
    positions: tuple[Position, ...]


class MutableAccount:
    def __init__(self, quantities):
        self.quantities = list(quantities)
        self.calls = 0

    def refresh(self):
        index = min(self.calls, len(self.quantities) - 1)
        self.calls += 1
        quantity = self.quantities[index]
        positions = () if quantity == 0 else (Position("3911", quantity),)
        return State(positions)


class Broker:
    def __init__(self, *, state=3, cancel_error=None, remain_active=False):
        self.state = state
        self.cancel_error = cancel_error
        self.remain_active = remain_active
        self.cancel_calls = 0

    def orders(self, *, product=0):
        return (
            {
                "ID": "OID",
                "Symbol": "3911",
                "Side": "1",
                "State": self.state,
                "LeavesQty": 100 if self.state != 5 else 0,
            },
        )

    def cancel_order(self, order_id):
        self.cancel_calls += 1
        if self.cancel_error:
            raise self.cancel_error
        if not self.remain_active:
            self.state = 5
        return {"Result": 0, "OrderId": order_id}


def build(account, broker):
    exit_service = LiveProtectiveExitService(
        account_state_provider=account,
        market_price_provider=lambda _code: 190,
        now_provider=lambda: NOW,
    )
    return LiveProtectiveExitConflictResolver(
        conflict_service=LiveExitOrderConflictService(order_reader=broker),
        cancel_service=LiveProtectiveCancelService(client=broker),
        exit_service=exit_service,
    )


def test_cancel_then_replan_uses_fresh_smaller_position():
    account = MutableAccount([40])
    broker = Broker()
    result = build(account, broker).resolve_stop_loss(
        code="3911", stop_price=200, trading_date=DAY
    )
    assert result.decision is LiveConflictResolutionDecision.REPLANNED
    assert result.can_submit
    assert result.plan is not None
    assert result.plan.decision is LiveProtectiveExitDecision.EXIT_REQUIRED
    assert result.plan.quantity == 40
    assert result.plan.order is not None
    assert result.plan.order.quantity == 40
    assert broker.cancel_calls == 1
    assert account.calls == 1


def test_cancel_then_replan_zero_position_does_not_submit():
    account = MutableAccount([0])
    broker = Broker()
    result = build(account, broker).resolve_stop_loss(
        code="3911", stop_price=200, trading_date=DAY
    )
    assert result.decision is LiveConflictResolutionDecision.REPLANNED
    assert not result.can_submit
    assert result.plan is not None
    assert result.plan.decision is LiveProtectiveExitDecision.NO_POSITION
    assert broker.cancel_calls == 1


def test_ambiguous_cancel_blocks_without_replan():
    account = MutableAccount([100])
    broker = Broker(cancel_error=RuntimeError("timeout"))
    result = build(account, broker).resolve_stop_loss(
        code="3911", stop_price=200, trading_date=DAY
    )
    assert result.decision is LiveConflictResolutionDecision.BLOCKED
    assert result.plan is None
    assert broker.cancel_calls == 1
    assert account.calls == 0


def test_nonterminal_after_cancel_blocks_without_replan():
    account = MutableAccount([100])
    broker = Broker(remain_active=True)
    result = build(account, broker).resolve_stop_loss(
        code="3911", stop_price=200, trading_date=DAY
    )
    assert result.decision is LiveConflictResolutionDecision.BLOCKED
    assert result.plan is None
    assert broker.cancel_calls == 1
    assert account.calls == 0


def test_no_conflict_does_not_cancel_and_plans_from_live_position():
    account = MutableAccount([70])
    broker = Broker(state=5)
    result = build(account, broker).resolve_stop_loss(
        code="3911", stop_price=200, trading_date=DAY
    )
    assert result.decision is LiveConflictResolutionDecision.CLEAR
    assert result.can_submit
    assert result.plan is not None
    assert result.plan.quantity == 70
    assert broker.cancel_calls == 0
    assert account.calls == 1
