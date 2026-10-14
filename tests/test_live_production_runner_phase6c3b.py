from datetime import date

import pytest

from app.live.execution_mode import ExecutionModeSettings, TradingExecutionMode
from app.live.live_production_runner import (
    LiveCycleDecision,
    LiveEntryIntent,
    LiveProductionRunner,
    LiveProductionRunnerError,
)

DAY = date(2026, 10, 14)
CONFIRMATION = "KATANA-LIVE-2026-10-14"


def _settings(mode=TradingExecutionMode.LIVE, *, armed=True, confirmation=CONFIRMATION):
    return ExecutionModeSettings(
        mode=mode,
        live_armed=armed,
        live_confirmation=confirmation,
    )


def test_rejects_non_live_mode_before_any_cycle_action():
    calls = []
    runner = LiveProductionRunner(
        execution_settings=_settings(TradingExecutionMode.PAPER),
        entry_intent_provider=lambda: calls.append("signal") or (),
        entry_submitter=lambda *_: calls.append("submit"),
        protective_cycle=lambda *_: calls.append("protect"),
    )
    with pytest.raises(LiveProductionRunnerError):
        runner.run_cycle(trading_date=DAY)
    assert calls == []


def test_daily_arming_is_required_before_any_cycle_action():
    calls = []
    runner = LiveProductionRunner(
        execution_settings=_settings(armed=False),
        entry_intent_provider=lambda: calls.append("signal") or (),
        entry_submitter=lambda *_: calls.append("submit"),
        protective_cycle=lambda *_: calls.append("protect"),
    )
    with pytest.raises(Exception):
        runner.run_cycle(trading_date=DAY)
    assert calls == []


def test_protective_cycle_runs_before_new_entry_submission():
    calls = []
    runner = LiveProductionRunner(
        execution_settings=_settings(),
        entry_intent_provider=lambda: calls.append("signal") or (
            LiveEntryIntent("e1", "7203", 100),
        ),
        entry_submitter=lambda intent, day: calls.append(("submit", intent.code, day)) or object(),
        protective_cycle=lambda day: calls.append(("protect", day)),
    )
    result = runner.run_cycle(trading_date=DAY)
    assert calls[0] == ("protect", DAY)
    assert calls[1] == "signal"
    assert calls[2] == ("submit", "7203", DAY)
    assert result.decision is LiveCycleDecision.SUBMISSION_STARTED
    assert result.started_entries == 1


def test_no_signal_never_calls_submitter():
    calls = []
    runner = LiveProductionRunner(
        execution_settings=_settings(),
        entry_intent_provider=lambda: (),
        entry_submitter=lambda *_: calls.append("submit"),
        protective_cycle=lambda *_: None,
    )
    result = runner.run_cycle(trading_date=DAY)
    assert result.decision is LiveCycleDecision.NO_ACTION
    assert calls == []


def test_false_submit_result_is_not_counted_as_started():
    runner = LiveProductionRunner(
        execution_settings=_settings(),
        entry_intent_provider=lambda: (LiveEntryIntent("e1", "7203", 100),),
        entry_submitter=lambda *_: False,
        protective_cycle=lambda *_: None,
    )
    result = runner.run_cycle(trading_date=DAY)
    assert result.decision is LiveCycleDecision.BLOCKED
    assert result.started_entries == 0
