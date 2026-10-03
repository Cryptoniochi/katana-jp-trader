"""Phase 6-C Step 3B-2 mandatory safety-state tests."""

from datetime import date, datetime, timezone

from app.live.live_order_adapter import LockedLiveOrderAdapter
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


NOW = datetime(2026, 10, 3, 2, 30, 0, tzinfo=timezone.utc)


def _order() -> TradeOrder:
    return TradeOrder(
        order_id="order-missing-safety-1",
        signal_id="signal-missing-safety-1",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=2500.0,
        stop_price=None,
    )


def _portfolio() -> RiskPortfolioSnapshot:
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


def _kill_snapshot() -> KillSwitchSnapshot:
    return KillSwitchSnapshot(
        manual_blocked=False,
        daily_loss_blocked=False,
        consecutive_loss_blocked=False,
        runtime_health_ok=True,
        heartbeat_alive=True,
        broker_available=True,
        evaluated_at=NOW,
    )


def _adapter(tmp_path) -> LockedLiveOrderAdapter:
    return LockedLiveOrderAdapter(
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
        portfolio_provider=lambda: _portfolio(),
        kill_switch_snapshot_provider=lambda: _kill_snapshot(),
        idempotency_store=SQLiteLiveOrderIdempotencyStore(
            tmp_path / "katana.db",
            now_provider=lambda: NOW,
        ),
        safety_snapshot_provider=None,
        runtime_armed=True,
        now_provider=lambda: NOW,
    )


def test_missing_safety_provider_blocks_before_kill_switch_and_risk(
    tmp_path,
) -> None:
    adapter = _adapter(tmp_path)
    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.decision is LiveOrderDecision.BLOCKED
    assert result.reason is LiveOrderBlockReason.RECONCILIATION
    assert result.safety_snapshot is None
    assert result.kill_switch_evaluation is None
    assert result.risk_assessment is None


def test_missing_safety_provider_does_not_reserve_idempotency_key(
    tmp_path,
) -> None:
    database_path = tmp_path / "katana.db"
    adapter = _adapter(tmp_path)
    intent = adapter.create_intent(_order())

    first = adapter.evaluate(intent)
    second = adapter.evaluate(intent)

    assert first.decision is LiveOrderDecision.BLOCKED
    assert second.decision is LiveOrderDecision.BLOCKED
    assert second.reason is LiveOrderBlockReason.RECONCILIATION

    # A fresh store object over the same database still sees no reservation:
    # the missing-safety gate ran before idempotency persistence.
    store = SQLiteLiveOrderIdempotencyStore(
        database_path,
        now_provider=lambda: NOW,
    )
    fingerprint = LockedLiveOrderAdapter.create_order_fingerprint(intent.order)
    assert store.reserve(
        intent.idempotency_key,
        order_fingerprint=fingerprint,
        order_id=intent.order.order_id,
        signal_id=intent.order.signal_id,
    )
