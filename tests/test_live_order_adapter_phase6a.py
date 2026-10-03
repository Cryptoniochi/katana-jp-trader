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


def _order() -> TradeOrder:
    return TradeOrder(
        order_id="order-phase6a-1",
        signal_id="signal-phase6a-1",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=2500.0,
    )


def _adapter(*, snapshot=None, runtime_armed=False):
    return LockedLiveOrderAdapter(
        risk_manager=LiveRiskManager(),
        kill_switch_service=KillSwitchService(),
        portfolio_provider=_portfolio,
        kill_switch_snapshot_provider=lambda: (
            snapshot if snapshot is not None else KillSwitchSnapshot()
        ),
        idempotency_store=InMemoryLiveOrderIdempotencyStore(),
        runtime_armed=runtime_armed,
        now_provider=lambda: NOW,
    )


def test_phase6a_static_live_transmission_lock_is_off():
    assert LIVE_ORDER_TRANSMISSION_ENABLED is False


def test_default_adapter_stops_at_static_lock():
    adapter = _adapter()
    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.decision is LiveOrderDecision.LOCKED
    assert result.reason is LiveOrderBlockReason.STATIC_LOCK
    assert result.risk_assessment is None


def test_runtime_armed_cannot_override_phase6a_static_lock():
    adapter = _adapter(runtime_armed=True)
    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.decision is LiveOrderDecision.LOCKED
    assert result.reason is LiveOrderBlockReason.STATIC_LOCK


def test_kill_switch_precedes_static_lock():
    adapter = _adapter(
        snapshot=KillSwitchSnapshot(manual_blocked=True),
        runtime_armed=True,
    )
    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.decision is LiveOrderDecision.BLOCKED
    assert result.reason is LiveOrderBlockReason.KILL_SWITCH
    assert result.kill_switch_evaluation.is_blocked


def test_idempotency_key_is_stable_for_same_order():
    adapter = _adapter()
    order = _order()

    first = adapter.create_intent(order)
    second = adapter.create_intent(order)

    assert first.idempotency_key == second.idempotency_key


def test_idempotency_key_changes_when_order_content_changes():
    adapter = _adapter()
    first = _order()
    second = TradeOrder(
        order_id=first.order_id,
        signal_id=first.signal_id,
        code=first.code,
        side=first.side,
        order_type=first.order_type,
        quantity=200,
        limit_price=first.limit_price,
    )

    assert (
        adapter.create_idempotency_key(first)
        != adapter.create_idempotency_key(second)
    )


def test_in_memory_idempotency_store_rejects_second_reservation():
    store = InMemoryLiveOrderIdempotencyStore()

    assert store.reserve("same-key") is True
    assert store.reserve("same-key") is False


def test_adapter_exposes_no_submission_method():
    adapter = _adapter()

    assert not hasattr(adapter, "submit_order")
    assert not hasattr(adapter, "send_order")


def test_live_order_adapter_source_contains_no_broker_adapter_dependency():
    import inspect
    import app.live.live_order_adapter as module

    source = inspect.getsource(module)

    assert "BrokerAdapter" not in source
    assert "requests." not in source
    assert "urllib." not in source
