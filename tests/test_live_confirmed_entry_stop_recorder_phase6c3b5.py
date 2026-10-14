from datetime import date
from types import SimpleNamespace

import pytest

from app.live.live_confirmed_entry_stop_recorder import (
    LiveConfirmedEntryStopDecision,
    LiveConfirmedEntryStopRecorder,
)
from app.live.live_execution_position_consistency import (
    LiveExecutionPositionConsistencyDecision,
)
from app.live.live_execution_reconciliation import (
    LiveExecutionFill,
    LiveExecutionReconciliation,
    LiveExecutionReconciliationState,
)
from app.live.live_execution_tracking_flow import (
    LiveExecutionTrackingDecision,
    LiveExecutionTrackingResult,
)
from app.live.live_protective_stop_repository import SQLiteLiveProtectiveStopRepository
from app.live.live_submitted_execution_lifecycle import LiveSubmittedExecutionDecision
from app.trading.order_models import OrderSide, OrderType, TradeOrder

DAY=date(2026,10,14)


def order(side=OrderSide.BUY):
    return TradeOrder(order_id="o1", signal_id="s1", code="3911",
                      side=side, order_type=OrderType.MARKET, quantity=100)


def tracking(*, decision, cum, fills, position_confirmed=True, execution_key="s1"):
    state = (LiveExecutionReconciliationState.FILLED
             if decision is LiveExecutionTrackingDecision.FILLED_CONSISTENT
             else LiveExecutionReconciliationState.PARTIALLY_FILLED)
    recon=LiveExecutionReconciliation(
        broker_order_id="b1", state=state, order_quantity=100.0,
        cumulative_quantity=float(cum), remaining_quantity=float(100-cum),
        fills=tuple(fills), detail="test")
    lifecycle=SimpleNamespace(
        decision=(LiveSubmittedExecutionDecision.FILLED
                  if state is LiveExecutionReconciliationState.FILLED
                  else LiveSubmittedExecutionDecision.PARTIALLY_FILLED),
        reconciliation=recon)
    consistency=SimpleNamespace(
        decision=(LiveExecutionPositionConsistencyDecision.CONSISTENT
                  if position_confirmed
                  else LiveExecutionPositionConsistencyDecision.MISMATCH))
    return LiveExecutionTrackingResult(
        execution_key=execution_key, decision=decision,
        baseline=SimpleNamespace(code="3911", quantity=0),
        lifecycle=lifecycle, consistency=consistency)


def recorder(tmp_path):
    repo=SQLiteLiveProtectiveStopRepository(tmp_path/"katana.db")
    return repo, LiveConfirmedEntryStopRecorder(repository=repo)


def test_full_fill_uses_weighted_actual_execution_price(tmp_path):
    repo, r=recorder(tmp_path)
    result=r.record(
        execution_key="s1", order=order(), trading_date=DAY,
        tracking_result=tracking(
            decision=LiveExecutionTrackingDecision.FILLED_CONSISTENT,
            cum=100,
            fills=(LiveExecutionFill("e1",40,210), LiveExecutionFill("e2",60,212))))
    assert result.decision is LiveConfirmedEntryStopDecision.RECORDED
    assert result.record.quantity == 100
    assert result.record.fill_price == pytest.approx(211.2)
    assert result.record.stop_price == pytest.approx(209.088)
    assert repo.get_current("3911") == result.record


def test_partial_fill_is_protected_then_monotonically_updated(tmp_path):
    repo, r=recorder(tmp_path)
    first=r.record(
        execution_key="s1", order=order(), trading_date=DAY,
        tracking_result=tracking(
            decision=LiveExecutionTrackingDecision.PARTIALLY_FILLED_CONSISTENT,
            cum=40, fills=(LiveExecutionFill("e1",40,210),)))
    assert first.record.quantity == 40
    second=r.record(
        execution_key="s1", order=order(), trading_date=DAY,
        tracking_result=tracking(
            decision=LiveExecutionTrackingDecision.FILLED_CONSISTENT,
            cum=100,
            fills=(LiveExecutionFill("e1",40,210), LiveExecutionFill("e2",60,212))))
    assert second.record.quantity == 100
    assert second.record.fill_price == pytest.approx(211.2)
    assert len(repo.list_current()) == 1


def test_replaying_same_reconciliation_is_idempotent(tmp_path):
    repo, r=recorder(tmp_path)
    t=tracking(decision=LiveExecutionTrackingDecision.PARTIALLY_FILLED_CONSISTENT,
               cum=40, fills=(LiveExecutionFill("e1",40,210),))
    a=r.record(execution_key="s1", order=order(), trading_date=DAY, tracking_result=t)
    b=r.record(execution_key="s1", order=order(), trading_date=DAY, tracking_result=t)
    assert a.record == b.record
    assert len(repo.list_current()) == 1


@pytest.mark.parametrize("decision", [
    LiveExecutionTrackingDecision.WORKING_CONSISTENT,
    LiveExecutionTrackingDecision.UNKNOWN,
    LiveExecutionTrackingDecision.POSITION_MISMATCH,
])
def test_unconfirmed_or_inconsistent_state_never_creates_stop(tmp_path, decision):
    repo, r=recorder(tmp_path)
    result=r.record(
        execution_key="s1", order=order(), trading_date=DAY,
        tracking_result=tracking(
            decision=decision, cum=0, fills=(), position_confirmed=False))
    assert result.decision is LiveConfirmedEntryStopDecision.NO_CONFIRMED_FILL
    assert repo.list_current() == ()


def test_missing_fill_details_fail_closed_even_when_cumulative_is_full(tmp_path):
    repo, r=recorder(tmp_path)
    result=r.record(
        execution_key="s1", order=order(), trading_date=DAY,
        tracking_result=tracking(
            decision=LiveExecutionTrackingDecision.FILLED_CONSISTENT,
            cum=100, fills=()))
    assert result.decision is LiveConfirmedEntryStopDecision.BLOCKED
    assert repo.list_current() == ()


def test_fill_detail_quantity_must_equal_broker_cumulative(tmp_path):
    repo, r=recorder(tmp_path)
    result=r.record(
        execution_key="s1", order=order(), trading_date=DAY,
        tracking_result=tracking(
            decision=LiveExecutionTrackingDecision.FILLED_CONSISTENT,
            cum=100, fills=(LiveExecutionFill("e1",90,211),)))
    assert result.decision is LiveConfirmedEntryStopDecision.BLOCKED
    assert repo.list_current() == ()


def test_sell_reconciliation_never_creates_entry_stop(tmp_path):
    repo, r=recorder(tmp_path)
    result=r.record(
        execution_key="s1", order=order(OrderSide.SELL), trading_date=DAY,
        tracking_result=tracking(
            decision=LiveExecutionTrackingDecision.FILLED_CONSISTENT,
            cum=100, fills=(LiveExecutionFill("e1",100,211),)))
    assert result.decision is LiveConfirmedEntryStopDecision.NOT_BUY
    assert repo.list_current() == ()


def test_execution_key_mismatch_fails_closed(tmp_path):
    repo, r=recorder(tmp_path)
    result=r.record(
        execution_key="s1", order=order(), trading_date=DAY,
        tracking_result=tracking(
            decision=LiveExecutionTrackingDecision.FILLED_CONSISTENT,
            cum=100, fills=(LiveExecutionFill("e1",100,211),),
            execution_key="other"))
    assert result.decision is LiveConfirmedEntryStopDecision.BLOCKED
    assert repo.list_current() == ()
