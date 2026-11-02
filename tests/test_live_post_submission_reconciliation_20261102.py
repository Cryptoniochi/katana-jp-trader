from datetime import date
from types import SimpleNamespace

from app.live.execution_mode import ExecutionModeSettings, TradingExecutionMode
from app.live.live_production_runner import (
    LiveCycleDecision,
    LiveEntryIntent,
    LiveProductionRunner,
)


DAY = date(2026, 11, 2)
SETTINGS = ExecutionModeSettings(
    mode=TradingExecutionMode.LIVE,
    live_armed=True,
    live_confirmation="KATANA-LIVE-2026-11-02",
)


def test_successful_entry_is_reconciled_again_in_same_cycle():
    calls = []
    reconciliation_results = iter(
        (
            SimpleNamespace(blocked=0),
            SimpleNamespace(blocked=0),
        )
    )

    def reconcile(trading_date):
        calls.append("reconcile")
        return next(reconciliation_results)

    runner = LiveProductionRunner(
        execution_settings=SETTINGS,
        reconciliation_cycle=reconcile,
        protective_cycle=lambda d: calls.append("protect") or SimpleNamespace(blocked=0),
        entry_intent_provider=lambda: (
            calls.append("signal")
            or (LiveEntryIntent("entry-1", "7203", 100),)
        ),
        entry_submitter=lambda *_: calls.append("submit") or object(),
    )

    result = runner.run_cycle(trading_date=DAY)

    assert calls == [
        "reconcile",
        "protect",
        "signal",
        "protect",
        "submit",
        "reconcile",
    ]
    assert result.decision is LiveCycleDecision.SUBMISSION_STARTED
    assert result.started_entries == 1


def test_post_submission_reconciliation_failure_blocks_cycle():
    calls = []
    reconciliation_results = iter(
        (
            SimpleNamespace(blocked=0),
            SimpleNamespace(blocked=1),
        )
    )

    def reconcile(trading_date):
        calls.append("reconcile")
        return next(reconciliation_results)

    runner = LiveProductionRunner(
        execution_settings=SETTINGS,
        reconciliation_cycle=reconcile,
        protective_cycle=lambda d: calls.append("protect") or SimpleNamespace(blocked=0),
        entry_intent_provider=lambda: (
            calls.append("signal")
            or (LiveEntryIntent("entry-1", "7203", 100),)
        ),
        entry_submitter=lambda *_: calls.append("submit") or object(),
    )

    result = runner.run_cycle(trading_date=DAY)

    assert calls == [
        "reconcile",
        "protect",
        "signal",
        "protect",
        "submit",
        "reconcile",
    ]
    assert result.decision is LiveCycleDecision.BLOCKED
    assert result.started_entries == 1
    assert "post-submission reconciliation is unresolved" in result.message


def test_blocked_entry_does_not_run_post_submission_reconciliation():
    calls = []

    runner = LiveProductionRunner(
        execution_settings=SETTINGS,
        reconciliation_cycle=lambda d: (
            calls.append("reconcile") or SimpleNamespace(blocked=0)
        ),
        protective_cycle=lambda d: calls.append("protect") or SimpleNamespace(blocked=0),
        entry_intent_provider=lambda: (
            calls.append("signal")
            or (LiveEntryIntent("entry-1", "7203", 100),)
        ),
        entry_submitter=lambda *_: calls.append("submit") or False,
    )

    result = runner.run_cycle(trading_date=DAY)

    assert calls == [
        "reconcile",
        "protect",
        "signal",
        "protect",
        "submit",
    ]
    assert result.decision is LiveCycleDecision.BLOCKED
    assert result.started_entries == 0
