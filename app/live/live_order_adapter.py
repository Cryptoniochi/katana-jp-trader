"""Phase 6-A locked live-order adapter.

Safety invariant:
- no broker adapter is accepted;
- no network transport exists;
- no real-order submission method exists;
- every otherwise-valid order terminates at LOCKED.

This is intentionally a preparation/revalidation boundary only.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from app.live.live_order_models import (
    LiveOrderBlockReason,
    LiveOrderBoundaryResult,
    LiveOrderDecision,
    LiveOrderIntent,
)
from app.live.risk_manager import LiveRiskManager
from app.live.risk_models import RiskPortfolioSnapshot
from app.risk.kill_switch_models import KillSwitchSnapshot
from app.risk.kill_switch_service import KillSwitchService
from app.trading.order_models import OrderSide, TradeOrder
from app.trading.signal_models import SignalAction, TradeSignal


# Phase 6-A compile-time/default lock. It must remain False in this phase.
LIVE_ORDER_TRANSMISSION_ENABLED = False


class LiveOrderIdempotencyStore(Protocol):
    """Durable reservation contract for live-order idempotency keys."""

    def reserve(self, idempotency_key: str) -> bool:
        """Return True only when the key is newly reserved."""


class InMemoryLiveOrderIdempotencyStore:
    """Test/development store. Production composition should use durable storage."""

    def __init__(self) -> None:
        self._keys: set[str] = set()

    def reserve(self, idempotency_key: str) -> bool:
        key = idempotency_key.strip()
        if not key:
            raise ValueError("idempotency_key must not be empty.")
        if key in self._keys:
            return False
        self._keys.add(key)
        return True


PortfolioProvider = Callable[[], RiskPortfolioSnapshot]
KillSwitchSnapshotProvider = Callable[[], KillSwitchSnapshot]
NowProvider = Callable[[], datetime]


class LockedLiveOrderAdapter:
    """Live order boundary that cannot transmit orders in Phase 6-A."""

    def __init__(
        self,
        *,
        risk_manager: LiveRiskManager,
        kill_switch_service: KillSwitchService,
        portfolio_provider: PortfolioProvider,
        kill_switch_snapshot_provider: KillSwitchSnapshotProvider,
        idempotency_store: LiveOrderIdempotencyStore,
        runtime_armed: bool = False,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.risk_manager = risk_manager
        self.kill_switch_service = kill_switch_service
        self.portfolio_provider = portfolio_provider
        self.kill_switch_snapshot_provider = kill_switch_snapshot_provider
        self.idempotency_store = idempotency_store
        self.runtime_armed = bool(runtime_armed)
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    @staticmethod
    def create_idempotency_key(order: TradeOrder) -> str:
        """Create a stable key from immutable order content."""

        payload = "|".join(
            (
                order.order_id,
                order.signal_id,
                order.code,
                order.side.value,
                order.order_type.value,
                str(order.quantity),
                repr(order.limit_price),
                repr(order.stop_price),
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def create_intent(self, order: TradeOrder) -> LiveOrderIntent:
        """Create an auditable immutable live-order intent."""

        return LiveOrderIntent(
            order=order,
            idempotency_key=self.create_idempotency_key(order),
            created_at=self._current_time(),
        )

    def evaluate(self, intent: LiveOrderIntent) -> LiveOrderBoundaryResult:
        """Revalidate an intent and stop at the Phase 6-A locked boundary."""

        evaluated_at = self._current_time()

        # Emergency stop is checked before risk logic, including exits.
        kill_evaluation = self.kill_switch_service.evaluate(
            self.kill_switch_snapshot_provider()
        )
        if kill_evaluation.is_blocked:
            return LiveOrderBoundaryResult(
                intent=intent,
                decision=LiveOrderDecision.BLOCKED,
                reason=LiveOrderBlockReason.KILL_SWITCH,
                evaluated_at=evaluated_at,
                risk_assessment=None,
                kill_switch_evaluation=kill_evaluation,
                message=(
                    "Live order blocked by Kill Switch: "
                    f"{kill_evaluation.reason.value}"
                ),
            )

        # Phase 6-A default/static lock is intentionally evaluated before
        # reserving the idempotency key, so dry locked checks do not consume it.
        if not LIVE_ORDER_TRANSMISSION_ENABLED:
            return LiveOrderBoundaryResult(
                intent=intent,
                decision=LiveOrderDecision.LOCKED,
                reason=LiveOrderBlockReason.STATIC_LOCK,
                evaluated_at=evaluated_at,
                risk_assessment=None,
                kill_switch_evaluation=kill_evaluation,
                message="Live order transmission is statically locked in Phase 6-A.",
            )

        if not self.runtime_armed:
            return LiveOrderBoundaryResult(
                intent=intent,
                decision=LiveOrderDecision.LOCKED,
                reason=LiveOrderBlockReason.RUNTIME_LOCK,
                evaluated_at=evaluated_at,
                risk_assessment=None,
                kill_switch_evaluation=kill_evaluation,
                message="Live order transmission is not armed at runtime.",
            )

        # This branch is unreachable while the Phase 6-A static lock is intact.
        signal = self._signal_from_order(intent.order, evaluated_at=evaluated_at)
        risk_assessment = self.risk_manager.assess(
            signal,
            portfolio=self.portfolio_provider(),
        )
        if not risk_assessment.is_approved:
            return LiveOrderBoundaryResult(
                intent=intent,
                decision=LiveOrderDecision.BLOCKED,
                reason=LiveOrderBlockReason.RISK_REVALIDATION,
                evaluated_at=evaluated_at,
                risk_assessment=risk_assessment,
                kill_switch_evaluation=kill_evaluation,
                message=(
                    "Live order blocked by final risk revalidation: "
                    f"{risk_assessment.reason.value}"
                ),
            )

        if not self.idempotency_store.reserve(intent.idempotency_key):
            return LiveOrderBoundaryResult(
                intent=intent,
                decision=LiveOrderDecision.DUPLICATE,
                reason=LiveOrderBlockReason.DUPLICATE,
                evaluated_at=evaluated_at,
                risk_assessment=risk_assessment,
                kill_switch_evaluation=kill_evaluation,
                message="Duplicate live-order intent blocked.",
            )

        # There is deliberately no transmission operation after this point.
        return LiveOrderBoundaryResult(
            intent=intent,
            decision=LiveOrderDecision.LOCKED,
            reason=LiveOrderBlockReason.STATIC_LOCK,
            evaluated_at=evaluated_at,
            risk_assessment=risk_assessment,
            kill_switch_evaluation=kill_evaluation,
            message="Phase 6-A has no live-order transport.",
        )

    @staticmethod
    def _signal_from_order(
        order: TradeOrder,
        *,
        evaluated_at: datetime,
    ) -> TradeSignal:
        """Build the existing risk-manager input from an order."""

        action = (
            SignalAction.BUY
            if order.side is OrderSide.BUY
            else SignalAction.SELL
        )

        # RiskManager requires a price. Limit/stop prices are usable when
        # present; MARKET orders intentionally cannot be fabricated here.
        signal_price = order.limit_price or order.stop_price
        if signal_price is None:
            raise ValueError(
                "Final live risk revalidation requires an explicit current "
                "price for MARKET orders. Phase 6-A does not fabricate one."
            )

        return TradeSignal(
            signal_id=order.signal_id,
            code=order.code,
            strategy_name="live_order_boundary",
            action=action,
            generated_at=evaluated_at,
            signal_price=signal_price,
            quantity=order.quantity,
        )

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current
