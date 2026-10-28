from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.live.live_execution_tracking_flow import LiveExecutionTrackingDecision
from app.live.live_protective_stop_repository import LiveProtectiveStopState
from app.live.live_strategy_exit_flow import (
    LiveStrategyExitDecision,
    LiveStrategyExitFlow,
)
from app.trading.order_models import OrderSide, OrderType, TradeOrder
from app.trading.signal_models import SignalAction, TradeSignal

DAY = date(2026, 10, 28)
NOW = datetime(2026, 10, 28, 5, 0, tzinfo=timezone.utc)


def signal(code="4395", signal_id="orb-v2-4395-exit-test"):
    return TradeSignal(
        signal_id=signal_id,
        code=code,
        strategy_name="orb",
        action=SignalAction.EXIT,
        generated_at=NOW,
        signal_price=1000.0,
        quantity=100,
        reason="take_profit",
    )


class Repo:
    def __init__(self, record=None):
        self.record = record
        self.pending_calls = []

    def get_current(self, code):
        return self.record if self.record and self.record.code == code else None

    def mark_exit_pending(self, **kwargs):
        self.pending_calls.append(kwargs)
        self.record.state = LiveProtectiveStopState.EXIT_PENDING
        self.record.exit_execution_key = kwargs["exit_execution_key"]
        self.record.exit_order_id = kwargs["exit_order_id"]
        return self.record


def owned(quantity=100, state=LiveProtectiveStopState.ACTIVE):
    return SimpleNamespace(
        code="4395",
        entry_execution_key="entry-4395",
        quantity=quantity,
        state=state,
        exit_execution_key=None,
        exit_order_id=None,
    )


class Resolver:
    def __init__(self, quantity=100, blocked=False):
        self.quantity = quantity
        self.blocked = blocked

    def resolve_eod(self, *, code, trading_date):
        if self.blocked:
            return SimpleNamespace(plan=None, message="unfinished SELL exists")
        order = TradeOrder(
            order_id="temporary-plan",
            signal_id="temporary-plan",
            code=code,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=self.quantity,
        )
        return SimpleNamespace(
            plan=SimpleNamespace(order=order),
            message="clear",
        )


class Tracking:
    def __init__(self, decision=LiveExecutionTrackingDecision.SUBMITTED):
        self.decision = decision
        self.calls = []

    def submit(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(decision=self.decision)


def build(record=None, broker_quantity=100, decision=LiveExecutionTrackingDecision.SUBMITTED):
    repo = Repo(record)
    tracking = Tracking(decision)
    flow = LiveStrategyExitFlow(
        ownership_repository=repo,
        conflict_resolver=Resolver(broker_quantity),
        prepared_tracking_flow=tracking,
    )
    return flow, repo, tracking


def test_no_katana_ownership_never_sells():
    flow, repo, tracking = build(record=None)
    result = flow.submit_signal(signal(), trading_date=DAY)
    assert result.decision is LiveStrategyExitDecision.NO_ACTION
    assert tracking.calls == []
    assert repo.pending_calls == []


def test_quantity_mismatch_blocks_before_submission():
    flow, repo, tracking = build(record=owned(100), broker_quantity=200)
    result = flow.submit_signal(signal(), trading_date=DAY)
    assert result.decision is LiveStrategyExitDecision.BLOCKED
    assert tracking.calls == []
    assert repo.pending_calls == []


def test_strategy_exit_uses_owned_quantity_and_marks_pending():
    flow, repo, tracking = build(record=owned(70), broker_quantity=70)
    result = flow.submit_signal(signal(), trading_date=DAY)
    assert result.decision is LiveStrategyExitDecision.SUBMISSION_STARTED
    assert len(tracking.calls) == 1
    call = tracking.calls[0]
    assert call["required_baseline_quantity"] == 70
    assert call["order"].side is OrderSide.SELL
    assert call["order"].order_type is OrderType.MARKET
    assert call["order"].quantity == 70
    assert call["execution_key"] == "strategy-exit:orb-v2-4395-exit-test"
    assert len(repo.pending_calls) == 1


def test_existing_exit_pending_never_resubmits():
    record = owned(100, LiveProtectiveStopState.EXIT_PENDING)
    record.exit_execution_key = "strategy-exit:old"
    record.exit_order_id = "old-order"
    flow, repo, tracking = build(record=record)
    result = flow.submit_signal(signal(), trading_date=DAY)
    assert result.decision is LiveStrategyExitDecision.BLOCKED
    assert tracking.calls == []


def test_submission_unknown_is_marked_pending_to_prevent_duplicate_sell():
    flow, repo, tracking = build(
        record=owned(100),
        decision=LiveExecutionTrackingDecision.SUBMISSION_UNKNOWN,
    )
    result = flow.submit_signal(signal(), trading_date=DAY)
    assert result.decision is LiveStrategyExitDecision.SUBMISSION_STARTED
    assert len(repo.pending_calls) == 1


def test_submission_blocked_does_not_mark_pending():
    flow, repo, tracking = build(
        record=owned(100),
        decision=LiveExecutionTrackingDecision.SUBMISSION_BLOCKED,
    )
    result = flow.submit_signal(signal(), trading_date=DAY)
    assert result.decision is LiveStrategyExitDecision.BLOCKED
    assert repo.pending_calls == []
