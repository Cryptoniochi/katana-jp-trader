from datetime import date, datetime, timezone

from app.live.live_order_adapter import LockedLiveOrderAdapter
from app.live.live_order_idempotency_repository import SQLiteLiveOrderIdempotencyStore
from app.live.live_order_models import LiveOrderBlockReason, LiveOrderDecision
from app.live.live_order_safety import LiveOrderSafetySnapshot
from app.live.risk_manager import LiveRiskManager
from app.live.risk_models import RiskPortfolioSnapshot
from app.risk.kill_switch_models import KillSwitchSnapshot
from app.risk.kill_switch_service import KillSwitchService
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 3, 2, 30, tzinfo=timezone.utc)


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
        order_id="phase6a-step3-order",
        signal_id="phase6a-step3-signal",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=1000.0,
        stop_price=None,
    )


def _adapter(tmp_path, snapshot):
    store = SQLiteLiveOrderIdempotencyStore(
        tmp_path / "katana.db",
        now_provider=lambda: NOW,
    )
    adapter = LockedLiveOrderAdapter(
        risk_manager=LiveRiskManager(),
        kill_switch_service=KillSwitchService(),
        portfolio_provider=_portfolio,
        kill_switch_snapshot_provider=_kill_snapshot,
        idempotency_store=store,
        safety_snapshot_provider=lambda: snapshot,
        runtime_armed=True,
        now_provider=lambda: NOW,
    )
    return adapter, store


def test_safe_stop_blocks_before_risk_and_idempotency(tmp_path):
    snapshot = LiveOrderSafetySnapshot(
        safe_stop_active=True,
        reconciliation_consistent=True,
        reconciliation_state="consistent",
        evaluated_at=NOW,
    )
    adapter, store = _adapter(tmp_path, snapshot)

    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.decision is LiveOrderDecision.BLOCKED
    assert result.reason is LiveOrderBlockReason.SAFE_STOP
    assert result.risk_assessment is None
    assert result.kill_switch_evaluation is None
    assert result.safety_snapshot is snapshot
    assert store.count() == 0


def test_reconciliation_abnormality_blocks_before_risk_and_idempotency(tmp_path):
    snapshot = LiveOrderSafetySnapshot(
        safe_stop_active=False,
        reconciliation_consistent=False,
        reconciliation_state="blocked",
        evaluated_at=NOW,
    )
    adapter, store = _adapter(tmp_path, snapshot)

    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.decision is LiveOrderDecision.BLOCKED
    assert result.reason is LiveOrderBlockReason.RECONCILIATION
    assert result.risk_assessment is None
    assert result.kill_switch_evaluation is None
    assert result.safety_snapshot is snapshot
    assert store.count() == 0


def test_safe_stop_has_priority_over_reconciliation_abnormality(tmp_path):
    snapshot = LiveOrderSafetySnapshot(
        safe_stop_active=True,
        reconciliation_consistent=False,
        reconciliation_state="blocked",
        evaluated_at=NOW,
    )
    adapter, store = _adapter(tmp_path, snapshot)

    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.reason is LiveOrderBlockReason.SAFE_STOP
    assert store.count() == 0


def test_healthy_emergency_state_preserves_step2_pipeline(tmp_path):
    snapshot = LiveOrderSafetySnapshot(
        safe_stop_active=False,
        reconciliation_consistent=True,
        reconciliation_state="consistent",
        evaluated_at=NOW,
    )
    adapter, store = _adapter(tmp_path, snapshot)

    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.decision is LiveOrderDecision.LOCKED
    assert result.reason is LiveOrderBlockReason.STATIC_LOCK
    assert result.risk_assessment is not None
    assert result.risk_assessment.is_approved
    assert result.kill_switch_evaluation is not None
    assert result.safety_snapshot is snapshot
    assert store.count() == 1


def test_adapter_still_has_no_live_submission_method():
    forbidden = {
        "submit_order",
        "send_order",
        "sendorder",
        "transmit",
        "execute_live_order",
    }
    assert forbidden.isdisjoint(dir(LockedLiveOrderAdapter))
