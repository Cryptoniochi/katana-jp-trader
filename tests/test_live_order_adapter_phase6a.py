from datetime import date, datetime, timezone

from app.live.live_order_adapter import (
    LIVE_ORDER_TRANSMISSION_ENABLED,
    InMemoryLiveOrderIdempotencyStore,
    LockedLiveOrderAdapter,
)
from app.live.live_order_models import (
    LiveOrderBlockReason,
    LiveOrderDecision,
)
from app.live.live_order_safety import LiveOrderSafetySnapshot
from app.live.risk_manager import LiveRiskManager
from app.live.risk_models import RiskPortfolioSnapshot
from app.risk.kill_switch_models import KillSwitchSnapshot
from app.risk.kill_switch_service import KillSwitchService
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 3, 0, 0, tzinfo=timezone.utc)


def _portfolio() -> RiskPortfolioSnapshot:
    return RiskPortfolioSnapshot(
        trading_date=date(2026, 10, 3),
        cash_balance=10_000_000.0,
        total_exposure=0.0,
        current_equity=10_000_000.0,
        peak_equity=10_000_000.0,
        daily_realized_profit_loss=0.0,
        consecutive_losses=0,
        open_position_codes=frozenset(),
    )


def _kill_snapshot(
    *,
    manual_blocked: bool = False,
) -> KillSwitchSnapshot:
    return KillSwitchSnapshot(
        manual_blocked=manual_blocked,
        daily_loss_blocked=False,
        consecutive_loss_blocked=False,
        runtime_health_ok=True,
        heartbeat_alive=True,
        broker_available=True,
        evaluated_at=NOW,
    )


def _safety_snapshot() -> LiveOrderSafetySnapshot:
    return LiveOrderSafetySnapshot(
        safe_stop_active=False,
        reconciliation_consistent=True,
        reconciliation_state="consistent",
        evaluated_at=NOW,
    )


def _order() -> TradeOrder:
    return TradeOrder(
        order_id="order-phase6a-1",
        signal_id="signal-phase6a-1",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=2_500.0,
        stop_price=None,
    )


def _adapter(
    *,
    runtime_armed: bool = False,
    manual_blocked: bool = False,
) -> LockedLiveOrderAdapter:
    return LockedLiveOrderAdapter(
        risk_manager=LiveRiskManager(),
        kill_switch_service=KillSwitchService(),
        portfolio_provider=_portfolio,
        kill_switch_snapshot_provider=lambda: _kill_snapshot(
            manual_blocked=manual_blocked
        ),
        idempotency_store=InMemoryLiveOrderIdempotencyStore(),
        safety_snapshot_provider=_safety_snapshot,
        runtime_armed=runtime_armed,
        now_provider=lambda: NOW,
    )


def test_phase6a_transmission_is_statically_disabled():
    assert LIVE_ORDER_TRANSMISSION_ENABLED is False


def test_default_adapter_revalidates_risk_then_stops_at_static_lock():
    adapter = _adapter()
    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.decision is LiveOrderDecision.LOCKED
    assert result.reason is LiveOrderBlockReason.STATIC_LOCK
    assert result.risk_assessment is not None
    assert result.risk_assessment.is_approved


def test_runtime_armed_cannot_defeat_static_lock():
    adapter = _adapter(runtime_armed=True)
    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.decision is LiveOrderDecision.LOCKED
    assert result.reason is LiveOrderBlockReason.STATIC_LOCK
    assert result.risk_assessment is not None
    assert result.risk_assessment.is_approved


def test_kill_switch_blocks_before_live_boundary_processing():
    adapter = _adapter(
        runtime_armed=True,
        manual_blocked=True,
    )
    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.decision is LiveOrderDecision.BLOCKED
    assert result.reason is LiveOrderBlockReason.KILL_SWITCH
    assert result.risk_assessment is None


def test_same_intent_is_duplicate_after_first_locked_evaluation():
    adapter = _adapter(runtime_armed=True)
    intent = adapter.create_intent(_order())

    first = adapter.evaluate(intent)
    second = adapter.evaluate(intent)

    assert first.decision is LiveOrderDecision.LOCKED
    assert first.reason is LiveOrderBlockReason.STATIC_LOCK
    assert second.decision is LiveOrderDecision.DUPLICATE
    assert second.reason is LiveOrderBlockReason.DUPLICATE


def test_idempotency_key_is_stable_for_same_order():
    order = _order()

    first = LockedLiveOrderAdapter.create_idempotency_key(order)
    second = LockedLiveOrderAdapter.create_idempotency_key(order)

    assert first == second


def test_adapter_exposes_no_live_submission_method():
    forbidden = {
        "submit_order",
        "send_order",
        "sendorder",
        "transmit",
        "execute_live_order",
    }

    assert forbidden.isdisjoint(dir(LockedLiveOrderAdapter))
