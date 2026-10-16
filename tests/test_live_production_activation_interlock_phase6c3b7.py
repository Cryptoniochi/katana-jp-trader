from types import SimpleNamespace
import pytest

from app.live.live_production_activation_interlock import (
    LIVE_PRODUCTION_ENABLE_VARIABLE,
    LiveProductionActivationInterlock,
)
from app.live.execution_mode import LiveTradingUnavailableError
from app.run_live_production import run_live_production


def test_legacy_static_hard_locks_remain_sealed():
    state = LiveProductionActivationInterlock.state({})
    assert state.legacy_locks_sealed is True
    assert state.production_activation_enabled is False
    assert state.released is False


def test_explicit_production_activation_releases_only_activated_path():
    state = LiveProductionActivationInterlock.require_released(
        {LIVE_PRODUCTION_ENABLE_VARIABLE: "YES"}
    )
    assert state.legacy_locks_sealed is True
    assert state.production_activation_enabled is True
    assert state.released is True


@pytest.mark.parametrize("value", ["", "NO", "TRUE", "1", "yes-please"])
def test_production_activation_is_fail_closed(value):
    with pytest.raises(RuntimeError):
        LiveProductionActivationInterlock.require_released(
            {LIVE_PRODUCTION_ENABLE_VARIABLE: value}
        )


def test_live_cli_fails_before_composition_without_production_activation(
    monkeypatch,
):
    called = []
    monkeypatch.setattr(
        "app.run_live_production.ConcreteLiveProductionFactory.create",
        lambda **kwargs: called.append(kwargs),
    )
    with pytest.raises(LiveTradingUnavailableError):
        run_live_production(
            [],
            settings=SimpleNamespace(live_armed=True),
            trading_date=None,
            environ={},
            output=None,
            error_output=None,
        )
    assert called == []
