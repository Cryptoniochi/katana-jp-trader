from datetime import date
from types import SimpleNamespace
from app.live.execution_mode import ExecutionModeSettings,TradingExecutionMode
from app.live.live_production_runner import LiveCycleDecision,LiveProductionRunner

DAY=date(2026,10,14)
SETTINGS=ExecutionModeSettings(mode=TradingExecutionMode.LIVE,live_armed=True,
 live_confirmation="KATANA-LIVE-2026-10-14")

def test_restart_safety_order_is_reconcile_guard_protect_entries():
    calls=[]
    runner=LiveProductionRunner(
      execution_settings=SETTINGS,
      reconciliation_cycle=lambda d: calls.append("reconcile") or SimpleNamespace(blocked=0),
      position_protection_reconciliation=lambda d: calls.append("guard") or SimpleNamespace(blocked=0),
      protective_cycle=lambda d: calls.append("protect") or SimpleNamespace(blocked=0),
      entry_intent_provider=lambda: calls.append("entries") or (),
      entry_submitter=lambda *_: calls.append("submit"))
    result=runner.run_cycle(trading_date=DAY)
    assert calls == ["reconcile","guard","protect","entries"]
    assert result.decision is LiveCycleDecision.NO_ACTION

def test_orphan_or_quantity_mismatch_guard_blocks_before_protect_and_entries():
    calls=[]
    runner=LiveProductionRunner(
      execution_settings=SETTINGS,
      reconciliation_cycle=lambda d: calls.append("reconcile") or SimpleNamespace(blocked=0),
      position_protection_reconciliation=lambda d: calls.append("guard") or SimpleNamespace(blocked=1),
      protective_cycle=lambda d: calls.append("protect"),
      entry_intent_provider=lambda: calls.append("entries") or (),
      entry_submitter=lambda *_: calls.append("submit"))
    result=runner.run_cycle(trading_date=DAY)
    assert result.decision is LiveCycleDecision.BLOCKED
    assert calls == ["reconcile","guard"]
