"""Phase 6-C Step 4C-3 locked-live runtime attachment tests."""

from __future__ import annotations

import inspect
from pathlib import Path

from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
    LockedLiveRuntimeIntegration,
)
from app.runtime.paper_trading_composition import (
    PaperTradingComposition,
    PaperTradingProductionBundle,
)


def test_phase6c_integration_hard_lock_remains_disabled() -> None:
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False


def test_disabled_attachment_creates_inert_integration_without_database_io(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"

    integration = LockedLiveRuntimeIntegration.disabled_attachment(
        database_path=database,
    )

    assert integration.enabled is False
    assert integration.database_path == database
    assert not database.exists()


def test_disabled_attachment_does_not_fabricate_reconciliation_state(
    tmp_path: Path,
) -> None:
    integration = LockedLiveRuntimeIntegration.disabled_attachment(
        database_path=tmp_path / "katana.db",
    )

    assert integration.reconciliation_report_provider() is None
    assert integration.fault_tolerance_attempt_provider() is None


def test_disabled_attachment_portfolio_state_is_fail_closed(
    tmp_path: Path,
) -> None:
    integration = LockedLiveRuntimeIntegration.disabled_attachment(
        database_path=tmp_path / "katana.db",
    )

    try:
        integration.portfolio_provider()
    except RuntimeError as error:
        assert "not connected" in str(error)
    else:
        raise AssertionError("portfolio provider must fail closed")


def test_disabled_attachment_kill_switch_state_is_fail_closed(
    tmp_path: Path,
) -> None:
    integration = LockedLiveRuntimeIntegration.disabled_attachment(
        database_path=tmp_path / "katana.db",
    )

    try:
        integration.kill_switch_snapshot_provider()
    except RuntimeError as error:
        assert "not connected" in str(error)
    else:
        raise AssertionError("kill-switch provider must fail closed")


def test_paper_composition_constructs_only_disabled_attachment() -> None:
    source = inspect.getsource(PaperTradingComposition.create)

    assert "LockedLiveRuntimeIntegration.disabled_attachment(" in source
    assert "locked_live_runtime_integration=None" not in source
    assert ".process(" not in source


def test_paper_bundle_run_does_not_touch_locked_live_integration() -> None:
    source = inspect.getsource(PaperTradingProductionBundle.run)

    assert "locked_live_runtime_integration" not in source
    assert ".process(" not in source


def test_paper_composition_does_not_construct_live_execution_pipeline() -> None:
    source = inspect.getsource(PaperTradingComposition.create)

    forbidden = (
        "FreshLockedLiveRuntimeFactory.create",
        "LockedLiveBrokerTransport(",
        "LockedLiveSubmissionCoordinator(",
        "LiveExecutionClaimGate(",
        "SQLiteLiveExecutionJournal(",
        "SQLiteLiveOrderIdempotencyStore(",
    )
    for pattern in forbidden:
        assert pattern not in source


def test_integration_still_exposes_no_transport_method() -> None:
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
