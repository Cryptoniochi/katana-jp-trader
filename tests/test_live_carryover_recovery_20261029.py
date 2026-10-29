from datetime import date
from types import SimpleNamespace

from app.live.execution_mode import ExecutionModeSettings, TradingExecutionMode
from app.live.live_production_runner import (
    LiveCycleDecision,
    LiveProductionRunner,
)


DAY = date(2026, 10, 30)

SETTINGS = ExecutionModeSettings(
    mode=TradingExecutionMode.LIVE,
    live_armed=True,
    live_confirmation="KATANA-LIVE-2026-10-30",
)


class Ownership:
    def __init__(self, records):
        self.records = tuple(records)

    def list_current(self):
        return self.records


class CarryoverFlow:
    def __init__(self, records, decision="complete"):
        self.ownership_repository = Ownership(records)
        self.decision = decision
        self.calls = []

    def submit_all(self, *, trading_date):
        self.calls.append(trading_date)
        return SimpleNamespace(decision=self.decision)


def old_record():
    return SimpleNamespace(
        code="9603",
        quantity=100,
        trading_date=date(2026, 10, 29),
    )


def current_record():
    return SimpleNamespace(
        code="7203",
        quantity=100,
        trading_date=DAY,
    )


def test_prior_day_carryover_is_liquidated_before_guard_and_entries():
    calls = []
    flow = CarryoverFlow([old_record()])

    runner = LiveProductionRunner(
        execution_settings=SETTINGS,
        reconciliation_cycle=lambda d: calls.append("reconcile")
        or SimpleNamespace(blocked=0),
        position_protection_reconciliation=lambda d: calls.append("guard")
        or SimpleNamespace(blocked=0),
        protective_cycle=lambda d: calls.append("protect")
        or SimpleNamespace(blocked=0),
        entry_intent_provider=lambda: calls.append("entries") or (),
        entry_submitter=lambda *_: calls.append("submit"),
        carryover_liquidation_flow=flow,
    )

    result = runner.run_cycle(trading_date=DAY)

    assert flow.calls == [DAY]
    assert calls == ["reconcile", "guard"]
    assert result.decision is LiveCycleDecision.NO_ACTION


def test_unresolved_carryover_blocks_before_guard_protect_and_entries():
    calls = []
    flow = CarryoverFlow([old_record()], decision="blocked")

    runner = LiveProductionRunner(
        execution_settings=SETTINGS,
        reconciliation_cycle=lambda d: calls.append("reconcile")
        or SimpleNamespace(blocked=0),
        position_protection_reconciliation=lambda d: calls.append("guard")
        or SimpleNamespace(blocked=0),
        protective_cycle=lambda d: calls.append("protect"),
        entry_intent_provider=lambda: calls.append("entries") or (),
        entry_submitter=lambda *_: calls.append("submit"),
        carryover_liquidation_flow=flow,
    )

    result = runner.run_cycle(trading_date=DAY)

    assert flow.calls == [DAY]
    assert calls == ["reconcile"]
    assert result.decision is LiveCycleDecision.BLOCKED


def test_current_day_position_does_not_trigger_carryover_liquidation():
    calls = []
    flow = CarryoverFlow([current_record()])

    runner = LiveProductionRunner(
        execution_settings=SETTINGS,
        reconciliation_cycle=lambda d: calls.append("reconcile")
        or SimpleNamespace(blocked=0),
        position_protection_reconciliation=lambda d: calls.append("guard")
        or SimpleNamespace(blocked=0),
        protective_cycle=lambda d: calls.append("protect")
        or SimpleNamespace(blocked=0),
        entry_intent_provider=lambda: calls.append("entries") or (),
        entry_submitter=lambda *_: calls.append("submit"),
        carryover_liquidation_flow=flow,
    )

    result = runner.run_cycle(trading_date=DAY)

    assert flow.calls == []
    assert calls == ["reconcile", "guard", "protect", "entries"]
    assert result.decision is LiveCycleDecision.NO_ACTION


def test_missing_ownership_boundary_fails_closed():
    calls = []
    flow = SimpleNamespace(
        submit_all=lambda **_: SimpleNamespace(decision="complete")
    )

    runner = LiveProductionRunner(
        execution_settings=SETTINGS,
        reconciliation_cycle=lambda d: calls.append("reconcile")
        or SimpleNamespace(blocked=0),
        position_protection_reconciliation=lambda d: calls.append("guard")
        or SimpleNamespace(blocked=0),
        protective_cycle=lambda d: calls.append("protect"),
        entry_intent_provider=lambda: calls.append("entries") or (),
        entry_submitter=lambda *_: calls.append("submit"),
        carryover_liquidation_flow=flow,
    )

    result = runner.run_cycle(trading_date=DAY)

    assert calls == ["reconcile"]
    assert result.decision is LiveCycleDecision.BLOCKED
