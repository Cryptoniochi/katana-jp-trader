"""Phase 6-C Step 4G final read-only live-runtime integration audit."""

from __future__ import annotations

import inspect

import app.live.live_broker_transport as transport_module
import app.live.locked_live_runtime_integration as integration_module
import app.runtime.paper_trading_composition as composition_module
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
    LockedLiveRuntimeIntegration,
)
from app.runtime.paper_trading_composition import (
    PaperTradingComposition,
    PaperTradingProductionBundle,
)


def test_phase6c_live_runtime_hard_lock_is_false() -> None:
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False


def test_phase6c_broker_transport_hard_lock_is_false() -> None:
    assert transport_module.LIVE_BROKER_TRANSPORT_ENABLED is False


def test_paper_runtime_uses_only_disabled_state_connected_attachment() -> None:
    source = inspect.getsource(PaperTradingComposition.create)

    assert "disabled_state_connected_attachment(" in source
    assert "LockedLiveRuntimeIntegration.disabled_attachment(" not in source
    assert ".process(" not in source


def test_paper_runtime_connects_existing_read_only_state_sources() -> None:
    source = inspect.getsource(PaperTradingComposition.create)

    required = (
        "LiveRuntimeReadOnlyProviderFactory.create",
        "SQLiteDailyTradeRepository",
        "runtime_session_service=runtime_session",
        "settings.live_read_only_report_path",
        "daily_profit_loss_provider=",
        "consecutive_loss_count_provider=",
        "runtime_health_ok_provider=",
        "heartbeat_alive_provider=",
        "broker_available_provider=",
        "max_daily_loss=settings.max_daily_loss",
    )
    for pattern in required:
        assert pattern in source


def test_manual_live_kill_switch_remains_unconnected_fail_closed() -> None:
    source = inspect.getsource(PaperTradingComposition.create)

    assert "manual_blocked_provider" not in source


def test_unconnected_live_safety_inputs_remain_fail_closed() -> None:
    source = inspect.getsource(PaperTradingComposition.create)

    assert "def unavailable_live_portfolio" in source
    assert "Live portfolio state is not connected in Phase 6-C." in source
    assert "reconciliation_report_provider=lambda: None" in source
    assert "fault_tolerance_attempt_provider=lambda: None" in source


def test_paper_runtime_never_constructs_live_execution_pipeline() -> None:
    source = inspect.getsource(composition_module)

    forbidden = (
        "FreshLockedLiveRuntimeFactory.create(",
        "LockedLiveRuntimeFactory.create(",
        "SQLiteLiveExecutionJournal(",
        "SQLiteLiveOrderIdempotencyStore(",
        "LockedLiveBrokerTransport(",
        "LockedLiveSubmissionCoordinator(",
        "LockedLiveSubmissionBoundary(",
        "LiveExecutionClaimGate(",
    )
    for pattern in forbidden:
        assert pattern not in source


def test_paper_runtime_does_not_collect_broker_state_over_network_for_live_safety() -> None:
    source = inspect.getsource(PaperTradingComposition.create)

    assert "KabuStationReadOnlyService" not in source
    assert ".collect()" not in source
    assert "issue_token()" not in source


def test_paper_bundle_run_never_touches_live_attachment() -> None:
    source = inspect.getsource(PaperTradingProductionBundle.run)

    assert "locked_live_runtime_integration" not in source
    assert ".process(" not in source


def test_locked_live_integration_exposes_no_runtime_transport_entrypoint() -> None:
    forbidden = {
        "send",
        "sendorder",
        "submit",
        "submit_order",
        "start",
        "run",
        "execute",
    }

    assert forbidden.isdisjoint(dir(LockedLiveRuntimeIntegration))


def test_locked_live_process_returns_before_state_or_execution_construction() -> None:
    source = inspect.getsource(LockedLiveRuntimeIntegration.process)

    assert "if not LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED:" in source
    assert "LockedLiveRuntimeIntegrationDecision.DISABLED" in source


def test_no_phase6c_runtime_setting_can_enable_live_orders() -> None:
    settings_source = inspect.getsource(
        composition_module.PaperTradingProductionSettings
    )
    integration_source = inspect.getsource(integration_module)

    forbidden_settings = (
        "locked_live_runtime_enabled",
        "live_runtime_enabled",
        "live_order_enabled",
        "live_broker_transport_enabled",
    )
    for pattern in forbidden_settings:
        assert pattern not in settings_source

    assert "LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED = False" in integration_source
