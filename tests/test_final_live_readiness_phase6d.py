"""Phase 6-D Step 5 final Live readiness gate tests."""

from datetime import date, datetime, timezone

from app.live.execution_mode import ExecutionModeSettings, TradingExecutionMode
from app.live.final_live_readiness import FinalLiveReadinessGate, FinalLiveReadinessState
from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.live_order_safety import LiveOrderSafetySnapshot
from app.live.locked_live_runtime_integration import LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED
from app.live.risk_models import RiskPortfolioSnapshot
from app.risk.kill_switch_models import KillSwitchSnapshot

NOW = datetime(2026, 10, 5, 7, 0, tzinfo=timezone.utc)
DAY = date(2026, 10, 5)


def _portfolio() -> RiskPortfolioSnapshot:
    return RiskPortfolioSnapshot(
        trading_date=DAY,
        cash_balance=1_000_000.0,
        total_exposure=0.0,
        current_equity=1_000_000.0,
        peak_equity=1_000_000.0,
        daily_realized_profit_loss=0.0,
        consecutive_losses=0,
        open_position_codes=frozenset(),
    )


def _safety() -> LiveOrderSafetySnapshot:
    return LiveOrderSafetySnapshot(
        safe_stop_active=False,
        reconciliation_consistent=True,
        reconciliation_state="consistent",
        evaluated_at=NOW,
    )


def _kill_switch() -> KillSwitchSnapshot:
    return KillSwitchSnapshot(
        manual_blocked=False,
        daily_loss_blocked=False,
        consecutive_loss_blocked=False,
        runtime_health_ok=True,
        heartbeat_alive=True,
        broker_available=True,
        evaluated_at=NOW,
    )


def _settings() -> ExecutionModeSettings:
    return ExecutionModeSettings(
        mode=TradingExecutionMode.LIVE,
        live_armed=True,
        live_confirmation="KATANA-LIVE-2026-10-05",
    )


def _gate(**overrides) -> FinalLiveReadinessGate:
    values = dict(
        manual_blocked_provider=lambda: False,
        daily_profit_loss_provider=lambda: 0.0,
        consecutive_loss_count_provider=lambda: 0,
        runtime_health_ok_provider=lambda: True,
        heartbeat_alive_provider=lambda: True,
        broker_available_provider=lambda: True,
        portfolio_provider=_portfolio,
        safety_snapshot_provider=_safety,
        kill_switch_snapshot_provider=_kill_switch,
        now_provider=lambda: NOW,
    )
    values.update(overrides)
    return FinalLiveReadinessGate(**values)


def test_all_safety_inputs_can_be_activation_ready_but_not_order_ready():
    report = _gate().check(execution_settings=_settings(), trading_date=DAY)
    assert report.activation_ready is True
    assert report.state is FinalLiveReadinessState.ACTIVATION_READY
    assert report.transport_ready is False
    assert report.live_order_ready is False
    assert all(item.passed for item in report.items)


def test_manual_kill_switch_blocks_activation():
    report = _gate(manual_blocked_provider=lambda: True).check(
        execution_settings=_settings(), trading_date=DAY
    )
    assert report.activation_ready is False
    assert {item.key: item.passed for item in report.items}["manual_kill_switch"] is False


def test_safety_snapshot_blocks_on_reconciliation_or_safe_stop():
    blocked = LiveOrderSafetySnapshot(
        safe_stop_active=True,
        reconciliation_consistent=False,
        reconciliation_state="safe_stop",
        evaluated_at=NOW,
    )
    report = _gate(safety_snapshot_provider=lambda: blocked).check(
        execution_settings=_settings(), trading_date=DAY
    )
    assert report.activation_ready is False
    assert {item.key: item.passed for item in report.items}["reconciliation_fault_tolerance"] is False


def test_provider_exception_fails_closed():
    def broken() -> bool:
        raise RuntimeError("unavailable")

    report = _gate(broker_available_provider=broken).check(
        execution_settings=_settings(), trading_date=DAY
    )
    item = next(x for x in report.items if x.key == "broker_availability")
    assert item.passed is False
    assert "RuntimeError" in item.message
    assert report.activation_ready is False


def test_daily_loss_limit_blocks_activation():
    report = _gate(daily_profit_loss_provider=lambda: -50_000.0).check(
        execution_settings=_settings(), trading_date=DAY
    )
    assert report.activation_ready is False


def test_consecutive_loss_limit_blocks_activation():
    report = _gate(consecutive_loss_count_provider=lambda: 3).check(
        execution_settings=_settings(), trading_date=DAY
    )
    assert report.activation_ready is False


def test_execution_mode_requires_daily_live_authorization():
    report = _gate().check(execution_settings=ExecutionModeSettings(), trading_date=DAY)
    item = next(x for x in report.items if x.key == "execution_mode_authorization")
    assert item.passed is False
    assert report.activation_ready is False


def test_phase6d_hard_locks_remain_closed():
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False
    assert LIVE_BROKER_TRANSPORT_ENABLED is False
