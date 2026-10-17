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
        self.batches = list(batches)
        self.reads = 0

    def plan_end_of_day(self, *, trading_date):
        self.reads += 1
        if not self.batches:
            return SimpleNamespace(plans=())
        value = self.batches.pop(0)
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(plans=tuple(value))


class Ownership:
    def __init__(self, quantities=None):
        self.quantities = dict(quantities or {})

    def list_current(self):
        return tuple(
            SimpleNamespace(code=code, quantity=quantity)
            for code, quantity in self.quantities.items()
        )


class Resolver:
    def __init__(self, quantities=None):
        self.quantities = dict(quantities or {})

    def resolve_eod(self, *, code, trading_date):
        quantity = self.quantities.get(code, 100)
        return SimpleNamespace(
            plan=plan(code, quantity),
            message="ok",
        )


class Execution:
    def __init__(self):
        self.calls = []

    def _submit_plan(self, *, plan, trading_date):
        self.calls.append((plan.code, plan.order.quantity))
        return SimpleNamespace(
            decision=LiveProtectiveExitExecutionDecision.SUBMISSION_STARTED
        )


def plan(code, quantity=100):
    return SimpleNamespace(
        code=code,
        order=SimpleNamespace(quantity=quantity),
    )


def flow(service, execution=None, ownership=None, resolver=None, max_passes=3):
    return LiveEodLiquidationFlow(
        exit_service=service,
        conflict_resolver=resolver or Resolver(),
        execution_flow=execution or Execution(),
        ownership_repository=ownership or Ownership({"3911": 100}),
        max_passes=max_passes,
    )


def test_eod_requires_fresh_empty_owned_read_before_complete():
    service = ExitService([[plan("3911")], []])
    execution = Execution()
    result = flow(service, execution=execution).submit_all(
        trading_date="2026-10-14"
    )
    assert result.decision is LiveEodExecutionDecision.COMPLETE
    assert service.reads == 2
    assert execution.calls == [("3911", 100)]


def test_eod_does_not_resubmit_owned_position_that_remains_after_submission():
    service = ExitService([[plan("3911")], [plan("3911")], []])
    execution = Execution()
    result = flow(service, execution=execution, max_passes=3).submit_all(
        trading_date="2026-10-14"
    )
    assert result.decision is LiveEodExecutionDecision.BLOCKED
    assert execution.calls == [("3911", 100)]
    assert service.reads == 2
    assert "no cancel or resubmission" in result.message


def test_eod_blocks_when_owned_position_never_reaches_flat_within_bound():
    service = ExitService([
        [plan("3911")],
        [plan("3911")],
        [plan("3911")],
    ])
    execution = Execution()
    result = flow(service, execution=execution, max_passes=2).submit_all(
        trading_date="2026-10-14"
    )
    assert result.decision is LiveEodExecutionDecision.BLOCKED
    assert execution.calls == [("3911", 100)]
    assert service.reads == 2
    assert "3911" in result.message


def test_eod_blocks_if_final_owned_verification_cannot_read_account():
    service = ExitService([[plan("3911")], RuntimeError("broker unavailable")])
    result = flow(service, max_passes=1).submit_all(
        trading_date="2026-10-14"
    )
    assert result.decision is LiveEodExecutionDecision.BLOCKED
    assert "verification" in result.message.lower()


def test_eod_rejects_unbounded_or_zero_pass_configuration():
    for value in (0, -1, False):
        try:
            LiveEodLiquidationFlow(
                exit_service=ExitService([]),
                conflict_resolver=Resolver(),
                execution_flow=Execution(),
                ownership_repository=Ownership(),
                max_passes=value,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {value!r}")


def test_unmanaged_live_position_is_never_submitted_and_does_not_prevent_complete():
    service = ExitService([[plan("8306", 100)]])
    execution = Execution()
    result = flow(
        service,
        execution=execution,
        ownership=Ownership({}),
    ).submit_all(trading_date="2026-10-14")
    assert result.decision is LiveEodExecutionDecision.COMPLETE
    assert execution.calls == []
    assert "unmanaged positions were not touched" in result.message


def test_owned_and_unmanaged_positions_only_submit_owned_symbol():
    service = ExitService([
        [plan("3911", 100), plan("8306", 200)],
        [plan("8306", 200)],
    ])
    execution = Execution()
    result = flow(
        service,
        execution=execution,
        ownership=Ownership({"3911": 100}),
    ).submit_all(trading_date="2026-10-14")
    assert result.decision is LiveEodExecutionDecision.COMPLETE
    assert execution.calls == [("3911", 100)]


def test_same_symbol_quantity_mismatch_blocks_without_sell():
    service = ExitService([[plan("3911", 200)]])
    execution = Execution()
    result = flow(
        service,
        execution=execution,
        ownership=Ownership({"3911": 100}),
    ).submit_all(trading_date="2026-10-14")
    assert result.decision is LiveEodExecutionDecision.BLOCKED
    assert execution.calls == []
    assert "broker=200, owned=100" in result.message


def test_resolver_replan_quantity_growth_blocks_before_sell():
    service = ExitService([[plan("3911", 100)]])
    execution = Execution()
    result = flow(
        service,
        execution=execution,
        ownership=Ownership({"3911": 100}),
        resolver=Resolver({"3911": 200}),
    ).submit_all(trading_date="2026-10-14")
    assert result.decision is LiveEodExecutionDecision.BLOCKED
    assert execution.calls == []
    assert "broker=200, owned=100" in result.message
