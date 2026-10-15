from types import SimpleNamespace
import pytest

from app.live.live_production_activation_interlock import (
    LiveProductionActivationInterlock,
)
from app.live.execution_mode import LiveTradingUnavailableError
from app.run_live_production import run_live_production


def test_current_static_hard_locks_keep_concrete_live_blocked():
    state=LiveProductionActivationInterlock.state()
    assert state.released is False
    with pytest.raises(RuntimeError):
        LiveProductionActivationInterlock.require_released()


def test_live_cli_fails_before_composition_while_hard_locks_closed(monkeypatch):
    called=[]
    monkeypatch.setattr(
        "app.run_live_production.ConcreteLiveProductionFactory.create",
        lambda **kwargs: called.append(kwargs),
    )
    with pytest.raises(LiveTradingUnavailableError):
        run_live_production(
            [],settings=SimpleNamespace(),trading_date=None,environ={},
            output=None,error_output=None)
    assert called == []
