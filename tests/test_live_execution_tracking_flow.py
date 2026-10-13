from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.live.activated_live_submission_coordinator import ActivatedLiveSubmissionDecision
from app.live.live_account_state_service import LiveAccountState, LiveCashPosition
from app.live.live_execution_position_consistency import LiveExecutionPositionConsistencyService
from app.live.live_execution_reconciliation import LiveExecutionReconciliation, LiveExecutionReconciliationState
from app.live.live_execution_tracking_flow import (
    LiveExecutionTrackingDecision,
    LiveExecutionTrackingFlow,
    LivePositionBaselineConflictError,
    SQLiteLivePositionBaselineRepository,
)
from app.live.live_submitted_execution_lifecycle import LiveSubmittedExecutionDecision
from app.trading.order_models import OrderSide, OrderType, TradeOrder

NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)
DAY = date(2026, 10, 13)


def _order(side=OrderSide.BUY):
    return TradeOrder(order_id="o1", signal_id="s1", code="3911", side=side,
                      order_type=OrderType.LIMIT, quantity=100, limit_price=211.0)


def _state(qty):
    positions = () if qty == 0 else (LiveCashPosition(code="3911", quantity=qty, average_price=211.0, current_price=211.0),)
    return LiveAccountState(generated_at=NOW, cash_balance=900000.0, positions=positions, orders=())


class Account:
    def __init__(self, *values): self.values=list(values); self.calls=0
    def refresh(self):
        self.calls += 1
        value=self.values.pop(0)
        if isinstance(value, Exception): raise value
        return value


class Submission:
    def __init__(self, decision=ActivatedLiveSubmissionDecision.SUBMITTED): self.decision=decision; self.calls=0
    def submit(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(decision=self.decision)


class Lifecycle:
    def __init__(self, state, cum): self.state=state; self.cum=cum; self.calls=0
    def reconcile(self, execution_key):
        self.calls += 1
        recon=LiveExecutionReconciliation(broker_order_id="b1", state=self.state,
            order_quantity=100.0, cumulative_quantity=float(self.cum), remaining_quantity=float(100-self.cum), fills=(), detail="test")
        mapping={
            LiveExecutionReconciliationState.ACCEPTED: LiveSubmittedExecutionDecision.WORKING,
            LiveExecutionReconciliationState.PARTIALLY_FILLED: LiveSubmittedExecutionDecision.PARTIALLY_FILLED,
            LiveExecutionReconciliationState.FILLED: LiveSubmittedExecutionDecision.FILLED,
            LiveExecutionReconciliationState.TERMINATED_UNFILLED: LiveSubmittedExecutionDecision.TERMINATED_UNFILLED,
            LiveExecutionReconciliationState.TERMINATED_PARTIAL: LiveSubmittedExecutionDecision.TERMINATED_PARTIAL,
            LiveExecutionReconciliationState.UNKNOWN: LiveSubmittedExecutionDecision.UNKNOWN,
        }
        return SimpleNamespace(decision=mapping[self.state], reconciliation=recon)


def _flow(tmp_path, account, submission=None, lifecycle=None):
    return LiveExecutionTrackingFlow(
        baseline_repository=SQLiteLivePositionBaselineRepository(tmp_path/"katana.db"),
        position_consistency_service=LiveExecutionPositionConsistencyService(account_state_service=account),
        submission_coordinator=submission or Submission(),
        submitted_lifecycle=lifecycle or Lifecycle(LiveExecutionReconciliationState.FILLED, 100),
    )


def test_submit_captures_and_persists_baseline_before_submission(tmp_path):
    account=Account(_state(200)); submission=Submission(); flow=_flow(tmp_path, account, submission)
    result=flow.submit(execution_key="e1", order=_order(), trading_date=DAY)
    assert result.decision is LiveExecutionTrackingDecision.SUBMITTED
    assert result.baseline.quantity == 200
    assert flow.baseline_repository.get_required("e1").quantity == 200
    assert account.calls == submission.calls == 1


def test_baseline_read_failure_prevents_submission(tmp_path):
    account=Account(RuntimeError("offline")); submission=Submission(); flow=_flow(tmp_path, account, submission)
    with pytest.raises(RuntimeError): flow.submit(execution_key="e1", order=_order(), trading_date=DAY)
    assert submission.calls == 0


def test_baseline_is_immutable_for_same_execution_key(tmp_path):
    account=Account(_state(100), _state(200)); flow=_flow(tmp_path, account)
    flow.submit(execution_key="e1", order=_order(), trading_date=DAY)
    with pytest.raises(LivePositionBaselineConflictError):
        flow.submit(execution_key="e1", order=_order(), trading_date=DAY)


def test_restart_can_reconcile_from_durable_baseline(tmp_path):
    first=_flow(tmp_path, Account(_state(200)))
    first.submit(execution_key="e1", order=_order(), trading_date=DAY)
    second=_flow(tmp_path, Account(_state(300)), lifecycle=Lifecycle(LiveExecutionReconciliationState.FILLED,100))
    result=second.reconcile(execution_key="e1", order=_order())
    assert result.decision is LiveExecutionTrackingDecision.FILLED_CONSISTENT
    assert result.position_confirmed is True
    assert result.may_retry_submission is False


def test_partial_fill_is_checked_against_real_position_delta(tmp_path):
    flow=_flow(tmp_path, Account(_state(100), _state(140)), lifecycle=Lifecycle(LiveExecutionReconciliationState.PARTIALLY_FILLED,40))
    flow.submit(execution_key="e1", order=_order(), trading_date=DAY)
    result=flow.reconcile(execution_key="e1", order=_order())
    assert result.decision is LiveExecutionTrackingDecision.PARTIALLY_FILLED_CONSISTENT
    assert result.consistency.actual_quantity == 140


def test_position_mismatch_fails_closed(tmp_path):
    flow=_flow(tmp_path, Account(_state(200), _state(250)))
    flow.submit(execution_key="e1", order=_order(), trading_date=DAY)
    result=flow.reconcile(execution_key="e1", order=_order())
    assert result.decision is LiveExecutionTrackingDecision.POSITION_MISMATCH
    assert result.position_confirmed is False
    assert result.may_retry_submission is False


def test_unknown_broker_state_fails_closed_without_position_refresh(tmp_path):
    account=Account(_state(0), _state(999))
    flow=_flow(tmp_path, account, lifecycle=Lifecycle(LiveExecutionReconciliationState.UNKNOWN,0))
    flow.submit(execution_key="e1", order=_order(), trading_date=DAY)
    result=flow.reconcile(execution_key="e1", order=_order())
    assert result.decision is LiveExecutionTrackingDecision.UNKNOWN
    assert account.calls == 1
    assert result.may_retry_submission is False


def test_sell_to_flat_is_confirmed(tmp_path):
    flow=_flow(tmp_path, Account(_state(100), _state(0)), lifecycle=Lifecycle(LiveExecutionReconciliationState.FILLED,100))
    flow.submit(execution_key="e1", order=_order(OrderSide.SELL), trading_date=DAY)
    result=flow.reconcile(execution_key="e1", order=_order(OrderSide.SELL))
    assert result.decision is LiveExecutionTrackingDecision.FILLED_CONSISTENT
    assert result.consistency.expected_quantity == 0
    assert result.consistency.actual_quantity == 0


def test_transport_blocked_still_has_durable_pretransport_baseline(tmp_path):
    flow=_flow(tmp_path, Account(_state(10)), submission=Submission(ActivatedLiveSubmissionDecision.TRANSPORT_BLOCKED))
    result=flow.submit(execution_key="e1", order=_order(), trading_date=DAY)
    assert result.decision is LiveExecutionTrackingDecision.SUBMISSION_BLOCKED
    assert flow.baseline_repository.get_required("e1").quantity == 10


def test_submission_unknown_never_grants_retry(tmp_path):
    flow=_flow(tmp_path, Account(_state(0)), submission=Submission(ActivatedLiveSubmissionDecision.UNKNOWN))
    result=flow.submit(execution_key="e1", order=_order(), trading_date=DAY)
    assert result.decision is LiveExecutionTrackingDecision.SUBMISSION_UNKNOWN
    assert result.may_retry_submission is False
