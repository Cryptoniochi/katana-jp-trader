"""Phase 6-C Step 3B-1 fail-closed tests for configured providers."""

from datetime import date, datetime, timezone

from app.live.live_order_adapter import LockedLiveOrderAdapter
from app.live.live_order_idempotency_repository import (
    SQLiteLiveOrderIdempotencyStore,
)
from app.live.live_order_models import (
    LiveOrderBlockReason,
    LiveOrderDecision,
)
from app.live.live_order_safety import LiveOrderSafetySnapshot
from app.live.risk_manager import LiveRiskManager
from app.live.risk_models import RiskLimits, RiskPortfolioSnapshot
from app.risk.kill_switch_models import KillSwitchSnapshot
from app.risk.kill_switch_service import KillSwitchService
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 3, 2, 0, 0, tzinfo=timezone.utc)


def _raise(message: str):
    raise RuntimeError(message)


def _order(*, order_type=OrderType.LIMIT) -> TradeOrder:
    return TradeOrder(
        order_id="order-fail-closed-1",
        signal_id="signal-fail-closed-1",
        code="7203",
        side=OrderSide.BUY,
        order_type=order_type,
        quantity=100,
        limit_price=2500.0 if order_type is OrderType.LIMIT else None,
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


def _safety() -> LiveOrderSafetySnapshot:
    return LiveOrderSafetySnapshot(
        safe_stop_active=False,
        reconciliation_consistent=True,
        reconciliation_state="consistent",
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


def _adapter(
    tmp_path,
    *,
    safety_provider=lambda: _safety(),
    kill_provider=lambda: _kill_snapshot(),
    portfolio_provider=lambda: _portfolio(),
    market_price_provider=None,
):
    return LockedLiveOrderAdapter(
        risk_manager=_risk_manager(),
        kill_switch_service=KillSwitchService(),
        portfolio_provider=portfolio_provider,
        kill_switch_snapshot_provider=kill_provider,
        idempotency_store=SQLiteLiveOrderIdempotencyStore(
            tmp_path / "katana.db",
            now_provider=lambda: NOW,
        ),
        market_price_provider=market_price_provider,
        safety_snapshot_provider=safety_provider,
        runtime_armed=False,
        now_provider=lambda: NOW,
    )


def test_configured_safety_provider_failure_is_blocked(tmp_path) -> None:
    adapter = _adapter(
        tmp_path,
        safety_provider=lambda: _raise("safety unavailable"),
    )
    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.decision is LiveOrderDecision.BLOCKED
    assert result.reason is LiveOrderBlockReason.RECONCILIATION
    assert result.safety_snapshot is None
    assert result.kill_switch_evaluation is None


def test_kill_switch_provider_failure_is_blocked(tmp_path) -> None:
    adapter = _adapter(
        tmp_path,
        kill_provider=lambda: _raise("kill state unavailable"),
    )
    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.decision is LiveOrderDecision.BLOCKED
    assert result.reason is LiveOrderBlockReason.KILL_SWITCH
    assert result.kill_switch_evaluation is None


def test_portfolio_provider_failure_is_blocked(tmp_path) -> None:
    adapter = _adapter(
        tmp_path,
        portfolio_provider=lambda: _raise("portfolio unavailable"),
    )
    result = adapter.evaluate(adapter.create_intent(_order()))

    assert result.decision is LiveOrderDecision.BLOCKED
    assert result.reason is LiveOrderBlockReason.RISK_REVALIDATION
    assert result.risk_assessment is None


def test_market_price_provider_failure_is_blocked(tmp_path) -> None:
    adapter = _adapter(
        tmp_path,
        market_price_provider=lambda _code: _raise("price unavailable"),
    )
    result = adapter.evaluate(
        adapter.create_intent(_order(order_type=OrderType.MARKET))
    )

    assert result.decision is LiveOrderDecision.BLOCKED
    assert result.reason is LiveOrderBlockReason.RISK_REVALIDATION
    assert result.risk_assessment is None


def test_missing_market_price_provider_is_blocked_for_market_order(
    tmp_path,
) -> None:
    adapter = _adapter(tmp_path, market_price_provider=None)
    result = adapter.evaluate(
        adapter.create_intent(_order(order_type=OrderType.MARKET))
    )

    assert result.decision is LiveOrderDecision.BLOCKED
    assert result.reason is LiveOrderBlockReason.RISK_REVALIDATION


def test_provider_failures_do_not_reserve_idempotency_key(tmp_path) -> None:
    database_path = tmp_path / "katana.db"
    store = SQLiteLiveOrderIdempotencyStore(
        database_path,
        now_provider=lambda: NOW,
    )
    adapter = LockedLiveOrderAdapter(
        risk_manager=_risk_manager(),
        kill_switch_service=KillSwitchService(),
        portfolio_provider=lambda: _raise("portfolio unavailable"),
        kill_switch_snapshot_provider=lambda: _kill_snapshot(),
        idempotency_store=store,
        safety_snapshot_provider=lambda: _safety(),
        now_provider=lambda: NOW,
    )
    intent = adapter.create_intent(_order())

    result = adapter.evaluate(intent)

    assert result.decision is LiveOrderDecision.BLOCKED

    healthy = LockedLiveOrderAdapter(
        risk_manager=_risk_manager(),
        kill_switch_service=KillSwitchService(),
        portfolio_provider=lambda: _portfolio(),
        kill_switch_snapshot_provider=lambda: _kill_snapshot(),
        idempotency_store=SQLiteLiveOrderIdempotencyStore(
            database_path,
            now_provider=lambda: NOW,
        ),
        safety_snapshot_provider=lambda: _safety(),
        now_provider=lambda: NOW,
    )
    retry = healthy.evaluate(healthy.create_intent(_order()))

    assert retry.decision is LiveOrderDecision.LOCKED
