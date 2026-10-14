from datetime import date
from types import SimpleNamespace

from app.live.execution_mode import ExecutionModeSettings, TradingExecutionMode
from app.live.live_production_runner import LiveCycleDecision, LiveEntryIntent, LiveProductionRunner

DAY=date(2026,10,14)
SETTINGS=ExecutionModeSettings(mode=TradingExecutionMode.LIVE,live_armed=True,
                               live_confirmation="KATANA-LIVE-2026-10-14")


def test_reconciliation_then_protection_then_signal_then_submit():
    calls=[]
    runner=LiveProductionRunner(
        execution_settings=SETTINGS,
        reconciliation_cycle=lambda d: calls.append("reconcile") or SimpleNamespace(blocked=0),
        protective_cycle=lambda d: calls.append("protect") or SimpleNamespace(blocked=0),
        entry_intent_provider=lambda: calls.append("signal") or (LiveEntryIntent("e","7203",100),),
        entry_submitter=lambda *_: calls.append("submit") or object())
    result=runner.run_cycle(trading_date=DAY)
    assert calls == ["reconcile","protect","signal","submit"]
    assert result.decision is LiveCycleDecision.SUBMISSION_STARTED


def test_unresolved_reconciliation_blocks_protection_and_new_risk():
    calls=[]
    runner=LiveProductionRunner(
        execution_settings=SETTINGS,
        reconciliation_cycle=lambda d: calls.append("reconcile") or SimpleNamespace(blocked=1),
        protective_cycle=lambda d: calls.append("protect"),
        entry_intent_provider=lambda: calls.append("signal") or (),
        entry_submitter=lambda *_: calls.append("submit"))
    result=runner.run_cycle(trading_date=DAY)
    assert result.decision is LiveCycleDecision.BLOCKED
    assert calls == ["reconcile"]


def test_unresolved_protection_blocks_signal_and_new_risk():
    calls=[]
    runner=LiveProductionRunner(
        execution_settings=SETTINGS,
        reconciliation_cycle=lambda d: SimpleNamespace(blocked=0),
        protective_cycle=lambda d: calls.append("protect") or SimpleNamespace(blocked=1),
        entry_intent_provider=lambda: calls.append("signal") or (),
        entry_submitter=lambda *_: calls.append("submit"))
    result=runner.run_cycle(trading_date=DAY)
    assert result.decision is LiveCycleDecision.BLOCKED
    assert calls == ["protect"]
