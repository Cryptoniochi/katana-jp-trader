from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.live.live_execution_tracking_flow import LiveExecutionTrackingDecision
from app.live.live_protective_exit_service import LiveProtectiveExitDecision
from app.live.live_protective_stop_cycle import LiveProtectiveStopCycle
from app.live.live_protective_stop_repository import (
    LiveProtectiveStopState,
    SQLiteLiveProtectiveStopRepository,
)


DAY=date(2026,10,16)


class Flow:
    def __init__(self, decision):
        self.decision=decision
        self.exit_service=self
    def reconcile(self, *, execution_key, order):
        return SimpleNamespace(decision=self.decision)
    def evaluate_stop_loss(self, **kwargs):
        return SimpleNamespace(decision=LiveProtectiveExitDecision.HOLD)
    def submit_stop_loss(self, **kwargs):
        raise AssertionError("EXIT_PENDING must never resubmit")


def _pending(tmp_path: Path):
    repo=SQLiteLiveProtectiveStopRepository(tmp_path/"katana.db")
    repo.record_filled_entry(
        code="3911",entry_execution_key="entry-1",trading_date=DAY,
        quantity=100,fill_price=211.0,
    )
    repo.mark_exit_pending(
        entry_execution_key="entry-1",
        exit_execution_key="protective-exit:exit-1",
        exit_order_id="exit-1",
    )
    return repo


def test_exit_pending_working_sell_remains_protected(tmp_path: Path):
    repo=_pending(tmp_path)
    result=LiveProtectiveStopCycle(
        repository=repo,
        execution_flow=Flow(LiveExecutionTrackingDecision.WORKING_CONSISTENT),
    )(DAY)
    assert result.blocked==0
    assert repo.get_current("3911").state is LiveProtectiveStopState.EXIT_PENDING


def test_exit_pending_terminal_sell_with_position_blocks_new_risk(tmp_path: Path):
    repo=_pending(tmp_path)
    result=LiveProtectiveStopCycle(
        repository=repo,
        execution_flow=Flow(LiveExecutionTrackingDecision.TERMINATED_CONSISTENT),
    )(DAY)
    assert result.blocked==1


def test_exit_pending_unknown_sell_with_position_blocks_new_risk(tmp_path: Path):
    repo=_pending(tmp_path)
    result=LiveProtectiveStopCycle(
        repository=repo,
        execution_flow=Flow(LiveExecutionTrackingDecision.UNKNOWN),
    )(DAY)
    assert result.blocked==1
