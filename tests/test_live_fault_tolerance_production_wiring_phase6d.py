"""Phase 6-D Step 3C production fault-tolerance state wiring audit."""

from pathlib import Path


def test_production_composition_connects_saved_fault_tolerance_state() -> None:
    source = Path("app/runtime/paper_trading_composition.py").read_text(encoding="utf-8")
    assert "fault_tolerance_state_path: Path = Path(" in source
    assert '"reports/live/fault_tolerance_state.json"' in source
    assert "fault_tolerance_state_path=(" in source
    assert "settings.fault_tolerance_state_path" in source
    assert ".fault_tolerance_attempt_provider" in source
    assert "fault_tolerance_attempt_provider=lambda: None" not in source


def test_step3c_keeps_live_runtime_hard_lock_closed() -> None:
    source = Path("app/live/locked_live_runtime_integration.py").read_text(
        encoding="utf-8"
    )
    assert "LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED = False" in source


def test_step3c_does_not_add_order_transport_to_read_only_composition() -> None:
    source = Path("app/live/live_runtime_read_only_composition.py").read_text(
        encoding="utf-8"
    )
    for token in (
        "sendorder",
        "LiveBrokerTransport(",
        "LockedLiveRuntimeFactory.create(",
        "FreshLockedLiveRuntimeFactory.create(",
        "KabuStationReadOnlyService(",
        ".collect(",
    ):
        assert token not in source
