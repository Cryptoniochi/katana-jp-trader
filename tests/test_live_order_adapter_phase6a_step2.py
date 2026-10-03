from datetime import date, datetime, timezone

from app.live.live_order_adapter import (
    LIVE_ORDER_TRANSMISSION_ENABLED,
    LockedLiveOrderAdapter,
)
from app.live.live_order_idempotency_repository import (
    SQLiteLiveOrderIdempotencyStore,
)
from app.live.live_order_models import (
    LiveOrderBlockReason,
    LiveOrderDecision,
)
from app.live.risk_manager import LiveRiskManager
from app.live.risk_models import RiskLimits, RiskPortfolioSnapshot
from app.risk.kill_switch_models import KillSwitchSnapshot
from app.risk.kill_switch_service import KillSwitchService
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 3, 1, 2, 3, tzinfo=timezone.utc)


def _portfolio(
    *,
    cash_balance=10_000_000.0,
    total_exposure=0.0,
    current_equity=10_000_000.0,
    peak_equity=10_000_000.0,
    daily_realized_profit_loss=0.0,
    consecutive_losses=0,
    open_position_codes=(),
):
    return RiskPortfolioSnapshot(
        trading_date=date(2026, 10, 3),
        cash_balance=cash_balance,
        total_exposure=total_exposure,
        current_equity=current_equity,
        peak_equity=peak_equity,
        daily_realized_profit_loss=daily_realized_profit_loss,
        consecutive_losses=consecutive_losses,
        open_position_codes=tuple(open_position_codes),
    )


def _kill_snapshot(*, manual_blocked=False):
    return KillSwitchSnapshot(
        manual_blocked=manual_blocked,
        daily_loss_blocked=False,
        consecutive_loss_blocked=False,
        runtime_health_ok=True,
        heartbeat_alive=True,
        broker_available=True,
        evaluated_at=NOW,
    )


def _order(*, order_id="order-1", signal_id="signal-1", quantity=100):
    return TradeOrder(
        order_id=order_id,
        signal_id=signal_id,
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        limit_price=1000.0,
        stop_price=None,
    )


def _adapter(
    tmp_path,
    *,
    portfolio=None,
    manual_blocked=False,
    runtime_armed=False,
):
    resolved_portfolio = portfolio or _portfolio()
    store = SQLiteLiveOrderIdempotencyStore(
        tmp_path / "katana.db",
        now_provider=lambda: NOW,
    )
    adapter = LockedLiveOrderAdapter(
        risk_manager=LiveRiskManager(
            limits=RiskLimits(
                max_position_count=5,
                max_position_value=1_000_000.0,
                max_total_exposure=5_000_000.0,
                minimum_cash_balance=500_000.0,
                max_daily_loss=50_000.0,
                max_drawdown_rate=0.10,
                max_consecutive_losses=3,
            )
        ),
        kill_switch_service=KillSwitchService(),
        portfolio_provider=lambda: resolved_portfolio,
        kill_switch_snapshot_provider=lambda: _kill_snapshot(
            manual_blocked=manual_blocked
        ),
        idempotency_store=store,
        runtime_armed=runtime_armed,
        now_provider=lambda: NOW,
    )
    return adapter, store


def test_phase6a_static_transmission_flag_remains_false():
    assert LIVE_ORDER_TRANSMISSION_ENABLED is False


def test_approved_order_is_risk_checked_reserved_and_static_locked(tmp_path):
    adapter, store = _adapter(tmp_path, runtime_armed=False)
    intent = adapter.create_intent(_order())

    result = adapter.evaluate(intent)

    assert result.decision is LiveOrderDecision.LOCKED
    assert result.reason is LiveOrderBlockReason.STATIC_LOCK
    assert result.risk_assessment is not None
    assert result.risk_assessment.is_approved
    assert store.count() == 1


def test_runtime_armed_still_ends_at_static_lock(tmp_path):
    adapter, store = _adapter(tmp_path, runtime_armed=True)
    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.decision is LiveOrderDecision.LOCKED
    assert result.reason is LiveOrderBlockReason.STATIC_LOCK
    assert result.risk_assessment is not None
    assert result.risk_assessment.is_approved
    assert store.count() == 1


def test_kill_switch_blocks_before_risk_and_reservation(tmp_path):
    adapter, store = _adapter(
        tmp_path,
        manual_blocked=True,
        runtime_armed=True,
    )
    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.decision is LiveOrderDecision.BLOCKED
    assert result.reason is LiveOrderBlockReason.KILL_SWITCH
    assert result.risk_assessment is None
    assert store.count() == 0


def test_final_risk_revalidation_blocks_before_reservation(tmp_path):
    adapter, store = _adapter(
        tmp_path,
        portfolio=_portfolio(
            daily_realized_profit_loss=-50_000.0,
        ),
        runtime_armed=True,
    )
    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.decision is LiveOrderDecision.BLOCKED
    assert result.reason is LiveOrderBlockReason.RISK_REVALIDATION
    assert result.risk_assessment is not None
    assert not result.risk_assessment.is_approved
    assert store.count() == 0


def test_duplicate_is_detected_after_restart(tmp_path):
    database_path = tmp_path / "katana.db"

    first, _ = _adapter(tmp_path, runtime_armed=True)
    first_result = first.evaluate(first.create_intent(_order()))
    assert first_result.decision is LiveOrderDecision.LOCKED

    second_store = SQLiteLiveOrderIdempotencyStore(
        database_path,
        now_provider=lambda: NOW,
    )
    second = LockedLiveOrderAdapter(
        risk_manager=LiveRiskManager(),
        kill_switch_service=KillSwitchService(),
        portfolio_provider=_portfolio,
        kill_switch_snapshot_provider=_kill_snapshot,
        idempotency_store=second_store,
        runtime_armed=True,
        now_provider=lambda: NOW,
    )

    result = second.evaluate(second.create_intent(_order()))

    assert result.decision is LiveOrderDecision.DUPLICATE
    assert result.reason is LiveOrderBlockReason.DUPLICATE
    assert second_store.count() == 1


def test_trade_signal_required_reason_is_supplied(tmp_path):
    adapter, _ = _adapter(tmp_path)
    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.risk_assessment is not None


def test_idempotency_key_is_stable():
    first = LockedLiveOrderAdapter.create_idempotency_key(_order())
    second = LockedLiveOrderAdapter.create_idempotency_key(_order())

    assert first == second


def test_idempotency_key_changes_when_order_content_changes():
    first = LockedLiveOrderAdapter.create_idempotency_key(_order(quantity=100))
    second = LockedLiveOrderAdapter.create_idempotency_key(_order(quantity=200))

    assert first != second


def test_adapter_has_no_submission_method():
    forbidden = {
        "submit_order",
        "send_order",
        "sendorder",
        "transmit",
        "execute_live_order",
    }

    assert forbidden.isdisjoint(dir(LockedLiveOrderAdapter))
