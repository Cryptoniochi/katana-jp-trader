from datetime import date
from types import SimpleNamespace
import pytest

from app.live.activated_live_submission_coordinator import ActivatedLiveSubmissionDecision
from app.live.live_execution_position_consistency import LivePositionBaseline
from app.live.live_execution_tracking_flow import (
    LiveExecutionTrackingFlow, LivePositionBaselineConflictError,
    SQLiteLivePositionBaselineRepository,
)
from app.trading.order_models import OrderSide, OrderType, TradeOrder

DAY=date(2026,10,13)

class PositionConsistency:
    def __init__(self, quantity): self.quantity=quantity
    def capture_baseline(self, order):
        return LivePositionBaseline(code=order.code,quantity=self.quantity)

class Submission:
    def __init__(self): self.calls=0
    def submit(self, **kwargs):
        self.calls+=1
        return SimpleNamespace(decision=ActivatedLiveSubmissionDecision.SUBMITTED)

def order():
    return TradeOrder(
        order_id="o1",signal_id="s1",code="3911",side=OrderSide.SELL,
        order_type=OrderType.MARKET,quantity=100
    )

def make(tmp_path, qty, submission):
    return LiveExecutionTrackingFlow(
        baseline_repository=SQLiteLivePositionBaselineRepository(tmp_path/"katana.db"),
        position_consistency_service=PositionConsistency(qty),
        submission_coordinator=submission,
        submitted_lifecycle=SimpleNamespace(),
    )

def test_guard_blocks_before_submission_and_persist(tmp_path):
    submission=Submission(); flow=make(tmp_path,80,submission)
    with pytest.raises(LivePositionBaselineConflictError):
        flow.submit(
            execution_key="e1",order=order(),trading_date=DAY,
            required_baseline_quantity=100
        )
    assert submission.calls == 0
    with pytest.raises(RuntimeError):
        flow.baseline_repository.get_required("e1")

def test_guard_allows_matching_fresh_baseline(tmp_path):
    submission=Submission(); flow=make(tmp_path,100,submission)
    result=flow.submit(
        execution_key="e1",order=order(),trading_date=DAY,
        required_baseline_quantity=100
    )
    assert submission.calls == 1
    assert result.baseline.quantity == 100
