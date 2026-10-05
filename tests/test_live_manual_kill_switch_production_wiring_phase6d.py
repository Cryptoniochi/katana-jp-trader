"""Phase 6-D Step 4C production manual Kill Switch wiring tests."""

from __future__ import annotations

import inspect
from pathlib import Path

from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)
from app.runtime.paper_trading_composition import (
    PaperTradingComposition,
    PaperTradingProductionSettings,
)


def test_settings_expose_durable_manual_kill_switch_path() -> None:
    source = inspect.getsource(PaperTradingProductionSettings)
    assert "manual_kill_switch_state_path" in source
    assert "reports/live/manual_kill_switch_state.json" in source


def test_manual_kill_switch_path_is_normalized_to_absolute_path() -> None:
    settings = PaperTradingProductionSettings(
        database_path=Path("data/katana.db"),
        codes=("7203",),
        kabu_station_api_password="test",
    )
    assert settings.manual_kill_switch_state_path.is_absolute()
    assert settings.manual_kill_switch_state_path.name == "manual_kill_switch_state.json"


def test_production_composition_passes_manual_state_path_to_provider_factory() -> None:
    source = inspect.getsource(PaperTradingComposition.create)
    assert "manual_kill_switch_state_path=(" in source
    assert "settings.manual_kill_switch_state_path" in source


def test_production_composition_connects_manual_blocked_provider() -> None:
    source = inspect.getsource(PaperTradingComposition.create)
    assert "manual_blocked_provider=(" in source
    assert ".manual_blocked_provider" in source


def test_manual_wiring_does_not_connect_writer_to_production() -> None:
    source = inspect.getsource(PaperTradingComposition.create)
    assert "ManualKillSwitchStateWriter" not in source
    assert ".engage(" not in source
    assert ".release(" not in source


def test_manual_wiring_does_not_add_live_execution_path() -> None:
    source = inspect.getsource(PaperTradingComposition.create)
    forbidden = (
        "FreshLockedLiveRuntimeFactory.create(",
        "LockedLiveRuntimeFactory.create(",
        "LockedLiveBrokerTransport(",
        "LockedLiveSubmissionCoordinator(",
        "LockedLiveSubmissionBoundary(",
        "LiveExecutionClaimGate(",
        ".process(",
    )
    for pattern in forbidden:
        assert pattern not in source


def test_hard_live_runtime_lock_remains_false() -> None:
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False
