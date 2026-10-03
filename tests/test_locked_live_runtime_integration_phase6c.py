"""Phase 6-C Step 4C-1 tests for the disabled runtime integration seam."""

from __future__ import annotations

import inspect
from datetime import date, datetime, timezone

import app.live.locked_live_runtime_integration as integration_module
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
    LockedLiveRuntimeIntegration,
    LockedLiveRuntimeIntegrationDecision,
)
from app.live.risk_manager import LiveRiskManager
from app.live.risk_models import RiskLimits, RiskPortfolioSnapshot
from app.risk.kill_switch_models import KillSwitchSnapshot
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 3, 5, 0, 0, tzinfo=timezone.utc)


def _portfolio():
    return RiskPortfolioSnapshot(
        trading_date=date(2026, 10, 3),
        cash_balance=10_000_000.0,
        total_exposure=0.0,
        current_equity=10_000_000.0,
        peak_equity=10_000_000.0,
        daily_realized_profit_loss=0.0,
        consecutive_losses=0,
        open_position_codes=(),
    )


def _kill_snapshot():
    return KillSwitchSnapshot(
        manual_blocked=False,
        daily_loss_blocked=False,
        consecutive_loss_blocked=False,
        runtime_health_ok=True,
        heartbeat_alive=True,
        broker_available=True,
        evaluated_at=NOW,
    )


def _order():
    return TradeOrder(
        order_id="step4c1-order",
        signal_id="step4c1-signal",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=2500.0,
        stop_price=None,
    )


def _integration(tmp_path, *, report_provider=None):
    return LockedLiveRuntimeIntegration(
        database_path=tmp_path / "katana.db",
        risk_manager=LiveRiskManager(limits=RiskLimits()),
        portfolio_provider=_portfolio,
        reconciliation_report_provider=(
            report_provider if report_provider is not None else lambda: None
        ),
        fault_tolerance_attempt_provider=lambda: None,
        kill_switch_snapshot_provider=_kill_snapshot,
        now_provider=lambda: NOW,
    )


def test_compile_time_integration_lock_is_false():
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False


def test_constructor_has_no_enabled_or_runtime_armed_override():
    parameters = inspect.signature(LockedLiveRuntimeIntegration).parameters

    assert "enabled" not in parameters
    assert "runtime_armed" not in parameters


def test_constructing_integration_does_not_create_database(tmp_path):
    integration = _integration(tmp_path)
    database_path = tmp_path / "katana.db"

    assert integration.enabled is False
    assert not database_path.exists()


def test_process_returns_disabled_without_creating_database(tmp_path):
    integration = _integration(tmp_path)
    database_path = tmp_path / "katana.db"

    result = integration.process(_order())

    assert result.decision is LockedLiveRuntimeIntegrationDecision.DISABLED
    assert result.is_disabled
    assert not database_path.exists()


def test_process_does_not_read_runtime_safety_providers(tmp_path):
    calls = {"report": 0}

    def report_provider():
        calls["report"] += 1
        raise AssertionError("disabled integration must not read safety state")

    integration = _integration(tmp_path, report_provider=report_provider)

    result = integration.process(_order())

    assert result.is_disabled
    assert calls["report"] == 0


def test_monkeypatching_compile_time_flag_still_has_no_activation_path(
    tmp_path,
    monkeypatch,
):
    integration = _integration(tmp_path)
    database_path = tmp_path / "katana.db"
    monkeypatch.setattr(
        integration_module,
        "LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED",
        True,
    )

    result = integration.process(_order())

    assert result.is_disabled
    assert not database_path.exists()


def test_integration_exposes_no_send_submit_or_start_method(tmp_path):
    integration = _integration(tmp_path)

    forbidden = (
        "send",
        "sendorder",
        "submit",
        "submit_order",
        "start",
        "run",
        "execute",
    )

    for name in forbidden:
        assert not hasattr(integration, name)


def test_module_does_not_reference_broker_or_network_transport():
    source = inspect.getsource(integration_module).lower()

    assert "brokeradapter" not in source
    assert "requests." not in source
    assert "urllib" not in source
    assert "httpx" not in source
    assert "sendorder(" not in source


def test_fresh_factory_is_imported_but_never_invoked_in_process(tmp_path, monkeypatch):
    calls = {"create": 0}

    def fail_if_called(*args, **kwargs):
        calls["create"] += 1
        raise AssertionError("FreshLockedLiveRuntimeFactory.create must stay dormant")

    monkeypatch.setattr(
        integration_module.FreshLockedLiveRuntimeFactory,
        "create",
        fail_if_called,
    )
    integration = _integration(tmp_path)

    result = integration.process(_order())

    assert result.is_disabled
    assert calls["create"] == 0
