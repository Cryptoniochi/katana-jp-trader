from datetime import date
from types import SimpleNamespace

from app.live.live_protective_exit_execution_flow import (
    LiveProtectiveExitExecutionDecision,
)
from app.live.live_protective_exit_service import LiveProtectiveExitDecision
from app.live.live_protective_stop_cycle import LiveProtectiveStopCycle
from app.live.live_protective_stop_repository import (
    LiveProtectiveStopState,
    SQLiteLiveProtectiveStopRepository,
)

DAY=date(2026,10,14)


class ExitService:
    def __init__(self, decision):
        self.decision=decision
        self.calls=[]
    def evaluate_stop_loss(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(decision=self.decision)


class Flow:
    def __init__(self, result_decision, plan_decision):
        self.exit_service=ExitService(plan_decision)
        self.result_decision=result_decision
        self.calls=[]
    def submit_stop_loss(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            decision=self.result_decision,
            plan=SimpleNamespace(decision=self.exit_service.decision),
        )


def make_repo(tmp_path):
    r=SQLiteLiveProtectiveStopRepository(tmp_path/"katana.db")
    r.record_filled_entry(code="3911", entry_execution_key="entry-1",
                          trading_date=DAY, quantity=100, fill_price=211.0)
    return r


def test_submission_moves_stop_to_pending_and_prevents_resubmit(tmp_path):
    r=make_repo(tmp_path)
    flow=Flow(LiveProtectiveExitExecutionDecision.SUBMISSION_STARTED,
              LiveProtectiveExitDecision.EXIT_REQUIRED)
    cycle=LiveProtectiveStopCycle(repository=r, execution_flow=flow)
    first=cycle(DAY)
    assert first.submitted == 1
    assert r.get_current("3911").state is LiveProtectiveStopState.EXIT_PENDING
    cycle(DAY)
    assert len(flow.calls) == 1


def test_pending_stop_retires_only_after_authoritative_no_position(tmp_path):
    r=make_repo(tmp_path)
    r.mark_exit_pending(entry_execution_key="entry-1")
    flow=Flow(LiveProtectiveExitExecutionDecision.NO_ACTION,
              LiveProtectiveExitDecision.NO_POSITION)
    result=LiveProtectiveStopCycle(repository=r, execution_flow=flow)(DAY)
    assert result.retired == 1
    assert r.get_current("3911") is None
    assert r.get_by_execution_key("entry-1").state is LiveProtectiveStopState.RETIRED


def test_pending_existing_position_never_resubmits(tmp_path):
    r=make_repo(tmp_path)
    r.mark_exit_pending(entry_execution_key="entry-1")
    flow=Flow(LiveProtectiveExitExecutionDecision.NO_ACTION,
              LiveProtectiveExitDecision.EXIT_REQUIRED)
    result=LiveProtectiveStopCycle(repository=r, execution_flow=flow)(DAY)
    assert result.submitted == 0
    assert flow.calls == []
    assert r.get_current("3911").state is LiveProtectiveStopState.EXIT_PENDING
