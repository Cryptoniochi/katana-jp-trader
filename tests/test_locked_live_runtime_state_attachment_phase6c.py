"""Phase 6-C Step 4C-4E state-connected disabled attachment tests."""

from datetime import date, datetime, timezone

from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
    LockedLiveRuntimeIntegration,
    LockedLiveRuntimeIntegrationDecision,
)
from app.live.risk_models import RiskPortfolioSnapshot
from app.risk.kill_switch_service import KillSwitchService
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 3, 1, 2, 3, tzinfo=timezone.utc)


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


def _order():
    return TradeOrder(
        order_id="order-4e",
        signal_id="signal-4e",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=1000.0,
        stop_price=None,
    )


def _attachment(*, manual=None, health=True, heartbeat=True, broker=True):
    return LockedLiveRuntimeIntegration.disabled_state_connected_attachment(
        database_path="data/katana.db",
        portfolio_provider=_portfolio,
        reconciliation_report_provider=lambda: None,
        fault_tolerance_attempt_provider=lambda: None,
        daily_profit_loss_provider=lambda: 0.0,
        consecutive_loss_count_provider=lambda: 0,
        runtime_health_ok_provider=lambda: health,
        heartbeat_alive_provider=lambda: heartbeat,
        broker_available_provider=lambda: broker,
        manual_blocked_provider=manual,
        now_provider=lambda: NOW,
    )


def test_phase6c_hard_lock_remains_false():
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False


def test_state_connected_attachment_remains_disabled():
    integration = _attachment(manual=lambda: False)
    result = integration.process(_order())
    assert result.decision is LockedLiveRuntimeIntegrationDecision.DISABLED


def test_process_does_not_evaluate_connected_state_while_disabled():
    calls = {"count": 0}

    def forbidden():
        calls["count"] += 1
        raise AssertionError("provider must not be called by disabled process")

    integration = LockedLiveRuntimeIntegration.disabled_state_connected_attachment(
        database_path="data/katana.db",
        portfolio_provider=forbidden,
        reconciliation_report_provider=forbidden,
        fault_tolerance_attempt_provider=forbidden,
        daily_profit_loss_provider=forbidden,
        consecutive_loss_count_provider=forbidden,
        runtime_health_ok_provider=forbidden,
        heartbeat_alive_provider=forbidden,
        broker_available_provider=forbidden,
        now_provider=lambda: NOW,
    )

    result = integration.process(_order())
    assert result.is_disabled
    assert calls["count"] == 0


def test_missing_manual_source_keeps_kill_switch_fail_closed():
    integration = _attachment()
    snapshot = integration.kill_switch_snapshot_provider()
    evaluation = KillSwitchService().evaluate(snapshot)
    assert evaluation.is_blocked
    assert evaluation.reason.value == "manual"


def test_healthy_connected_sources_can_form_active_snapshot_only_when_manual_connected():
    integration = _attachment(manual=lambda: False)
    snapshot = integration.kill_switch_snapshot_provider()
    evaluation = KillSwitchService().evaluate(snapshot)
    assert evaluation.allows_new_entries


def test_unhealthy_runtime_is_visible_in_connected_snapshot():
    integration = _attachment(manual=lambda: False, health=False)
    snapshot = integration.kill_switch_snapshot_provider()
    evaluation = KillSwitchService().evaluate(snapshot)
    assert evaluation.is_blocked
    assert evaluation.reason.value == "runtime_health"


def test_dead_heartbeat_is_visible_in_connected_snapshot():
    integration = _attachment(manual=lambda: False, heartbeat=False)
    snapshot = integration.kill_switch_snapshot_provider()
    evaluation = KillSwitchService().evaluate(snapshot)
    assert evaluation.is_blocked
    assert evaluation.reason.value == "heartbeat"


def test_broker_unavailable_is_visible_in_connected_snapshot():
    integration = _attachment(manual=lambda: False, broker=False)
    snapshot = integration.kill_switch_snapshot_provider()
    evaluation = KillSwitchService().evaluate(snapshot)
    assert evaluation.is_blocked
    assert evaluation.reason.value == "broker"


def test_legacy_disabled_attachment_still_exists_and_is_disabled(tmp_path):
    integration = LockedLiveRuntimeIntegration.disabled_attachment(
        database_path=tmp_path / "katana.db",
        now_provider=lambda: NOW,
    )
    assert integration.process(_order()).is_disabled
