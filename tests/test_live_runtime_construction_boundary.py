"""Tests for the Phase 6-F locked-live runtime construction boundary."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import inspect

from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.live_order_adapter import LIVE_ORDER_TRANSMISSION_ENABLED
from app.live.live_runtime_construction_boundary import LiveRuntimeConstructionBoundary
from app.live.live_runtime_integration_activation_gate import (
    LiveRuntimeIntegrationGateDecision,
    LiveRuntimeIntegrationGateReport,
)
from app.live.risk_manager import LiveRiskManager
from app.live.risk_models import RiskLimits, RiskPortfolioSnapshot
from app.risk.kill_switch_models import KillSwitchSnapshot


NOW = datetime(2026, 10, 10, 4, 0, tzinfo=timezone.utc)
TRADING_DATE = date(2026, 10, 10)


@dataclass(frozen=True)
class _Report:
    generated_at: datetime
    state: str = "consistent"
    consistent: bool = True
    live_order_ready: bool = False


def _gate(*, ready: bool) -> LiveRuntimeIntegrationGateReport:
    return LiveRuntimeIntegrationGateReport(
        generated_at=NOW,
        decision=(
            LiveRuntimeIntegrationGateDecision.READY_FOR_REVIEWED_UNLOCK
            if ready
            else LiveRuntimeIntegrationGateDecision.BLOCKED
        ),
        activation_prerequisites_ready=ready,
        legacy_hard_lock_closed=True,
        message="test gate",
    )


def _portfolio() -> RiskPortfolioSnapshot:
    return RiskPortfolioSnapshot(
        trading_date=TRADING_DATE,
        cash_balance=1_000_000.0,
        total_exposure=0.0,
        current_equity=1_000_000.0,
        peak_equity=1_000_000.0,
        daily_realized_profit_loss=0.0,
        consecutive_losses=0,
        open_position_codes=(),
    )


def _kill() -> KillSwitchSnapshot:
    return KillSwitchSnapshot(
        manual_blocked=False,
        daily_loss_blocked=False,
        consecutive_loss_blocked=False,
        runtime_health_ok=True,
        heartbeat_alive=True,
        broker_available=True,
        evaluated_at=NOW,
    )


def _risk_manager() -> LiveRiskManager:
    return LiveRiskManager(
        limits=RiskLimits(
            max_position_count=5,
            max_position_value=1_000_000.0,
            max_total_exposure=5_000_000.0,
            minimum_cash_balance=500_000.0,
            max_daily_loss=50_000.0,
            max_drawdown_rate=0.10,
            max_consecutive_losses=3,
        )
    )


def _construct(tmp_path, gate_report):
    return LiveRuntimeConstructionBoundary.construct(
        gate_report=gate_report,
        database_path=tmp_path / "katana.db",
        risk_manager=_risk_manager(),
        portfolio_provider=_portfolio,
        reconciliation_report_provider=lambda: _Report(generated_at=NOW),
        fault_tolerance_attempt_provider=lambda: None,
        kill_switch_snapshot_provider=_kill,
        now_provider=lambda: NOW,
    )


def test_blocked_gate_does_not_construct_or_create_database(tmp_path):
    result = _construct(tmp_path, _gate(ready=False))

    assert result.constructed is False
    assert result.bundle is None
    assert not (tmp_path / "katana.db").exists()


def test_ready_gate_constructs_fresh_locked_runtime(tmp_path):
    result = _construct(tmp_path, _gate(ready=True))

    assert result.constructed is True
    assert result.bundle is not None
    assert result.bundle.idempotency_store.database_path == tmp_path / "katana.db"
    assert result.bundle.journal.database_path == tmp_path / "katana.db"


def test_constructed_runtime_remains_disarmed(tmp_path):
    result = _construct(tmp_path, _gate(ready=True))
    bundle = result.bundle

    assert bundle is not None
    assert bundle.order_adapter.runtime_armed is False
    assert bundle.transport.runtime_armed is False
    assert LIVE_ORDER_TRANSMISSION_ENABLED is False
    assert LIVE_BROKER_TRANSPORT_ENABLED is False


def test_boundary_exposes_no_order_processing_or_transmission_api():
    forbidden = {
        "process", "run", "start", "execute", "send", "send_order",
        "sendorder", "submit", "submit_order", "transmit", "arm", "unlock",
    }
    assert forbidden.isdisjoint(dir(LiveRuntimeConstructionBoundary))


def test_boundary_source_contains_no_broker_or_network_dependency():
    source = inspect.getsource(LiveRuntimeConstructionBoundary)
    forbidden = (
        "BrokerAdapter",
        "http_client",
        "requests.",
        "kabu_station",
        "sendorder",
        "send_order",
    )
    assert all(name not in source for name in forbidden)
