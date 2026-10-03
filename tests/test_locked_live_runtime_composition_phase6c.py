"""Phase 6-C Step 4A tests for isolated locked-live runtime composition."""

from __future__ import annotations

import inspect
from datetime import date, datetime, timezone

from app.live.execution_mode import (
    ExecutionModeSettings,
    TradingExecutionMode,
)
from app.live.live_broker_transport import (
    LIVE_BROKER_TRANSPORT_ENABLED,
    LockedLiveBrokerTransport,
)
from app.live.live_execution_journal_models import LiveExecutionState
from app.live.live_order_adapter import (
    LIVE_ORDER_TRANSMISSION_ENABLED,
    LockedLiveOrderAdapter,
)
from app.live.live_order_models import LiveOrderDecision
from app.live.live_order_safety import LiveOrderSafetySnapshot
from app.live.locked_live_runtime_composition import LockedLiveRuntimeFactory
from app.live.risk_manager import LiveRiskManager
from app.live.risk_models import RiskLimits, RiskPortfolioSnapshot
from app.risk.kill_switch_models import KillSwitchSnapshot
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 3, 3, 30, 0, tzinfo=timezone.utc)
TRADING_DATE = date(2026, 10, 3)


def _portfolio() -> RiskPortfolioSnapshot:
    return RiskPortfolioSnapshot(
        trading_date=TRADING_DATE,
        cash_balance=10_000_000.0,
        total_exposure=0.0,
        current_equity=10_000_000.0,
        peak_equity=10_000_000.0,
        daily_realized_profit_loss=0.0,
        consecutive_losses=0,
        open_position_codes=(),
    )


def _safety() -> LiveOrderSafetySnapshot:
    return LiveOrderSafetySnapshot(
        safe_stop_active=False,
        reconciliation_consistent=True,
        reconciliation_state="consistent",
        evaluated_at=NOW,
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


def _order() -> TradeOrder:
    return TradeOrder(
        order_id="order-step4a-1",
        signal_id="signal-step4a-1",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=2500.0,
        stop_price=None,
    )


def _bundle(tmp_path, *, execution_settings=None):
    return LockedLiveRuntimeFactory.create(
        database_path=tmp_path / "katana.db",
        risk_manager=_risk_manager(),
        portfolio_provider=_portfolio,
        safety_snapshot_provider=_safety,
        kill_switch_snapshot_provider=_kill,
        execution_settings=execution_settings,
        now_provider=lambda: NOW,
    )


def test_factory_wires_one_durable_database_without_paper_runtime(tmp_path):
    bundle = _bundle(tmp_path)

    expected = tmp_path / "katana.db"
    assert bundle.idempotency_store.database_path == expected
    assert bundle.journal.database_path == expected

    signature = inspect.signature(LockedLiveRuntimeFactory.create)
    assert "paper_broker" not in signature.parameters
    assert "paper_trading_service" not in signature.parameters
    assert "live_orchestrator" not in signature.parameters


def test_factory_keeps_both_live_runtime_arms_disabled(tmp_path):
    bundle = _bundle(
        tmp_path,
        execution_settings=ExecutionModeSettings(
            mode=TradingExecutionMode.LIVE,
            live_armed=True,
            live_confirmation=f"KATANA-LIVE-{TRADING_DATE.isoformat()}",
        ),
    )

    assert bundle.order_adapter.runtime_armed is False
    assert bundle.transport.runtime_armed is False
    assert LIVE_ORDER_TRANSMISSION_ENABLED is False
    assert LIVE_BROKER_TRANSPORT_ENABLED is False


def test_composed_boundary_stops_at_lock_and_prepares_durably(tmp_path):
    bundle = _bundle(tmp_path)
    intent = bundle.order_adapter.create_intent(_order())

    result = bundle.preparation_service.prepare(intent)

    assert result.boundary_result.decision is LiveOrderDecision.LOCKED
    assert result.is_prepared
    assert result.journal_record is not None
    assert result.journal_record.state is LiveExecutionState.PREPARED
    assert bundle.idempotency_store.count() == 1
    assert bundle.journal.count() == 1


def test_composed_claim_gate_rechecks_safety_and_claims(tmp_path):
    bundle = _bundle(tmp_path)
    intent = bundle.order_adapter.create_intent(_order())
    prepared = bundle.preparation_service.prepare(intent)

    assert prepared.is_prepared

    claimed = bundle.claim_gate.claim(intent.idempotency_key)

    assert claimed.journal_record is not None
    assert claimed.journal_record.state is LiveExecutionState.CLAIMED


def test_full_composed_path_reaches_only_locked_transport(tmp_path):
    bundle = _bundle(tmp_path)
    order = _order()
    intent = bundle.order_adapter.create_intent(order)

    prepared = bundle.preparation_service.prepare(intent)
    assert prepared.is_prepared

    claimed = bundle.claim_gate.claim(intent.idempotency_key)
    assert claimed.journal_record is not None
    assert claimed.journal_record.state is LiveExecutionState.CLAIMED

    result = bundle.submission_coordinator.evaluate(
        execution_key=intent.idempotency_key,
        order=order,
        trading_date=TRADING_DATE,
    )

    record = bundle.journal.get_required(intent.idempotency_key)
    assert record.state is LiveExecutionState.SUBMISSION_PENDING
    assert record.submitted_at is None
    assert record.broker_order_id is None
    assert result.journal_record.state is LiveExecutionState.SUBMISSION_PENDING


def test_composition_does_not_expose_forbidden_send_methods(tmp_path):
    bundle = _bundle(tmp_path)
    forbidden = {
        "send",
        "send_order",
        "sendorder",
        "submit",
        "submit_order",
        "transmit",
        "execute_live_order",
    }

    for component in (
        bundle.order_adapter,
        bundle.preparation_service,
        bundle.claim_gate,
        bundle.submission_boundary,
        bundle.transport,
        bundle.submission_coordinator,
    ):
        public_names = {
            name.lower()
            for name in dir(component)
            if not name.startswith("_")
        }
        assert forbidden.isdisjoint(public_names)


def test_transport_constructor_accepts_no_broker_or_network_dependency():
    parameters = inspect.signature(
        LockedLiveBrokerTransport.__init__
    ).parameters

    forbidden = {
        "broker",
        "broker_adapter",
        "client",
        "http_client",
        "session",
        "kabu_station",
        "kabu_station_service",
    }
    assert forbidden.isdisjoint(parameters)
