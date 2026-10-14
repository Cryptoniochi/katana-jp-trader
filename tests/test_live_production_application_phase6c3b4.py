from types import SimpleNamespace
from datetime import date

import pytest

from app.live.execution_mode import ExecutionModeSettings, TradingExecutionMode
from app.live.live_production_application import (
    LiveProductionApplicationFactory,
    LiveProductionWiringError,
)


class Prepared:
    def __init__(self):
        self.calls=[]
    def submit(self, **kwargs):
        self.calls.append(kwargs)
        return object()


def settings(mode=TradingExecutionMode.LIVE):
    return ExecutionModeSettings(
        mode=mode,
        live_armed=True,
        live_confirmation="KATANA-LIVE-2026-10-14",
    )


def test_factory_rejects_non_live_mode():
    with pytest.raises(LiveProductionWiringError):
        LiveProductionApplicationFactory.create(
            execution_settings=settings(TradingExecutionMode.PAPER),
            final_runtime=SimpleNamespace(prepared_tracking_flow=Prepared()),
            entry_intent_provider=lambda: (),
            protective_cycle=lambda day: None,
        )


def test_factory_requires_final_live_runtime():
    with pytest.raises(LiveProductionWiringError):
        LiveProductionApplicationFactory.create(
            execution_settings=settings(),
            final_runtime=None,
            entry_intent_provider=lambda: (),
            protective_cycle=lambda day: None,
        )


def test_protective_cycle_runs_before_entry_provider():
    events=[]
    runtime=SimpleNamespace(prepared_tracking_flow=Prepared())
    app=LiveProductionApplicationFactory.create(
        execution_settings=settings(),
        final_runtime=runtime,
        entry_intent_provider=lambda: events.append("entries") or (),
        protective_cycle=lambda day: events.append("protective"),
    )
    app.run_cycle(trading_date=date(2026,10,14))
    assert events == ["protective","entries"]
