from types import SimpleNamespace

from app.live.live_eod_liquidation_flow import (
    LiveEodExecutionDecision,
    LiveEodLiquidationFlow,
)
from app.live.live_protective_exit_execution_flow import (
    LiveProtectiveExitExecutionDecision,
)


class ExitService:
    def __init__(self, batches):
        self.batches=list(batches)
        self.reads=0
    def plan_end_of_day(self, *, trading_date):
        self.reads += 1
        if not self.batches:
            return SimpleNamespace(plans=())
        value=self.batches.pop(0)
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(plans=tuple(value))


class Resolver:
    def resolve_eod(self, *, code, trading_date):
        return SimpleNamespace(plan=SimpleNamespace(code=code), message="ok")


class Execution:
    def __init__(self):
        self.calls=[]
    def _submit_plan(self, *, plan, trading_date):
        self.calls.append(plan.code)
        return SimpleNamespace(
            decision=LiveProtectiveExitExecutionDecision.SUBMISSION_STARTED
        )


def plan(code):
    return SimpleNamespace(code=code)


def test_eod_requires_fresh_empty_read_before_complete():
    service=ExitService([[plan("3911")], []])
    execution=Execution()
    result=LiveEodLiquidationFlow(
        exit_service=service,
        conflict_resolver=Resolver(),
        execution_flow=execution,
    ).submit_all(trading_date="2026-10-14")
    assert result.decision is LiveEodExecutionDecision.COMPLETE
    assert service.reads == 2
    assert execution.calls == ["3911"]


def test_eod_reprocesses_position_that_remains_after_first_pass():
    service=ExitService([[plan("3911")], [plan("3911")], []])
    execution=Execution()
    result=LiveEodLiquidationFlow(
        exit_service=service,
        conflict_resolver=Resolver(),
        execution_flow=execution,
        max_passes=3,
    ).submit_all(trading_date="2026-10-14")
    assert result.decision is LiveEodExecutionDecision.COMPLETE
    assert execution.calls == ["3911", "3911"]
    assert service.reads == 3


def test_eod_blocks_when_account_never_reaches_flat_within_bound():
    service=ExitService([
        [plan("3911")],
        [plan("3911")],
        [plan("3911")],
    ])
    execution=Execution()
    result=LiveEodLiquidationFlow(
        exit_service=service,
        conflict_resolver=Resolver(),
        execution_flow=execution,
        max_passes=2,
    ).submit_all(trading_date="2026-10-14")
    assert result.decision is LiveEodExecutionDecision.BLOCKED
    assert execution.calls == ["3911", "3911"]
    # Two work passes plus one final authoritative verification.
    assert service.reads == 3
    assert "3911" in result.message


def test_eod_blocks_if_final_flat_verification_cannot_read_account():
    service=ExitService([[plan("3911")], RuntimeError("broker unavailable")])
    result=LiveEodLiquidationFlow(
        exit_service=service,
        conflict_resolver=Resolver(),
        execution_flow=Execution(),
        max_passes=1,
    ).submit_all(trading_date="2026-10-14")
    assert result.decision is LiveEodExecutionDecision.BLOCKED
    assert "verification" in result.message.lower()


def test_eod_rejects_unbounded_or_zero_pass_configuration():
    for value in (0, -1, False):
        try:
            LiveEodLiquidationFlow(
                exit_service=ExitService([]),
                conflict_resolver=Resolver(),
                execution_flow=Execution(),
                max_passes=value,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {value!r}")
