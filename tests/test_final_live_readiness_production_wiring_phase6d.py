"""Phase 6-D Step 5B production Final Live Readiness wiring audit."""

from __future__ import annotations

import inspect

from app.live.final_live_readiness import FinalLiveReadinessGate
from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)
from app.runtime.paper_trading_composition import (
    PaperTradingComposition,
    PaperTradingProductionBundle,
)


def test_production_bundle_exposes_final_live_readiness_gate() -> None:
    fields = PaperTradingProductionBundle.__dataclass_fields__
    assert "final_live_readiness_gate" in fields


def test_production_composition_builds_runtime_safety_provider_from_real_sources() -> None:
    source = inspect.getsource(PaperTradingComposition.create)
    assert "LiveRuntimeSafetyStateProvider(" in source
    assert ".reconciliation_report_provider" in source
    assert ".fault_tolerance_attempt_provider" in source
    assert "reconciliation_report_provider=lambda: None" not in source
    assert "fault_tolerance_attempt_provider=lambda: None" not in source


def test_production_composition_builds_kill_switch_from_real_read_only_sources() -> None:
    source = inspect.getsource(PaperTradingComposition.create)
    assert "LiveRuntimeKillSwitchComposition(" in source
    assert ".manual_blocked_provider" in source
    assert ".daily_profit_loss_provider" in source
    assert ".consecutive_loss_count_provider" in source
    assert ".runtime_health_ok_provider" in source
    assert ".heartbeat_alive_provider" in source
    assert ".broker_available_provider" in source


def test_production_composition_builds_final_readiness_gate() -> None:
    source = inspect.getsource(PaperTradingComposition.create)
    assert "FinalLiveReadinessGate(" in source
    assert "safety_snapshot_provider=(" in source
    assert "kill_switch_snapshot_provider=(" in source
    assert "final_live_readiness_gate=(" in source


def test_final_readiness_gate_type_is_read_only_attachment() -> None:
    annotation = PaperTradingProductionBundle.__annotations__["final_live_readiness_gate"]
    assert "FinalLiveReadinessGate" in str(annotation)


def test_step5b_does_not_enable_live_hard_locks() -> None:
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False
    assert LIVE_BROKER_TRANSPORT_ENABLED is False


def test_step5b_does_not_add_live_order_submission_path() -> None:
    source = inspect.getsource(PaperTradingComposition.create)
    forbidden = (
        "sendorder",
        "FreshLockedLiveRuntimeFactory.create(",
        "LockedLiveRuntimeFactory.create(",
        "LockedLiveBrokerTransport(",
        "LockedLiveSubmissionCoordinator(",
        "LockedLiveSubmissionBoundary(",
        "LiveExecutionClaimGate(",
    )
    for pattern in forbidden:
        assert pattern not in source
