"""Phase 6-A locked live-order adapter.

Safety invariant:
- no broker adapter is accepted;
- no network transport exists;
- no real-order submission method exists;
- every otherwise-valid order terminates at LOCKED.

The boundary still performs emergency-stop evaluation, final risk revalidation,
and durable idempotency reservation before reporting the final lock state.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from app.live.live_order_idempotency_repository import (
    LiveOrderIdempotencyConflictError,
)
from app.live.live_order_safety import LiveOrderSafetySnapshot
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
    """Reservation contract for live-order idempotency keys."""

    def reserve(
        self,
        idempotency_key: str,
        *,
        order_fingerprint: str | None = None,
        order_id: str | None = None,
        signal_id: str | None = None,
    ) -> bool:
        """Return True only when the reservation is newly created."""


class InMemoryLiveOrderIdempotencyStore:
    """Test/development store with conflict detection."""

    def __init__(self) -> None:
        self._reservations: dict[str, tuple[str, str, str]] = {}

    def reserve(
        self,
        idempotency_key: str,
        *,
        order_fingerprint: str | None = None,
        order_id: str | None = None,
        signal_id: str | None = None,
    ) -> bool:
        key = self._required(idempotency_key, "idempotency_key")
        fingerprint = self._required(
            order_fingerprint if order_fingerprint is not None else key,
            "order_fingerprint",
        )
        resolved_order_id = self._required(
            order_id if order_id is not None else key,
            "order_id",
        )
        resolved_signal_id = self._required(
            signal_id if signal_id is not None else key,
            "signal_id",
        )
        candidate = (
            fingerprint,
            resolved_order_id,
            resolved_signal_id,
        )

        existing = self._reservations.get(key)
        if existing is None:
            self._reservations[key] = candidate
            return True
        if existing != candidate:
            raise LiveOrderIdempotencyConflictError(
                "Idempotency key is already bound to different order content: "
                f"{key}"
            )
        return False

    @staticmethod
    def _required(value: str, name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{name} must not be empty.")
        return normalized


PortfolioProvider = Callable[[], RiskPortfolioSnapshot]
KillSwitchSnapshotProvider = Callable[[], KillSwitchSnapshot]
MarketPriceProvider = Callable[[str], float]
SafetySnapshotProvider = Callable[[], LiveOrderSafetySnapshot]
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
        market_price_provider: MarketPriceProvider | None = None,
        safety_snapshot_provider: SafetySnapshotProvider | None = None,
        runtime_armed: bool = False,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.risk_manager = risk_manager
        self.kill_switch_service = kill_switch_service
        self.portfolio_provider = portfolio_provider
        self.kill_switch_snapshot_provider = kill_switch_snapshot_provider
        self.idempotency_store = idempotency_store
        self.market_price_provider = market_price_provider
        self.safety_snapshot_provider = safety_snapshot_provider
        self.runtime_armed = bool(runtime_armed)
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    @staticmethod
    def create_order_fingerprint(order: TradeOrder) -> str:
        """Create a stable fingerprint from immutable order content."""

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

    @classmethod
    def create_idempotency_key(cls, order: TradeOrder) -> str:
        """Create the stable Phase 6-A live-order idempotency key."""

        return cls.create_order_fingerprint(order)

    def create_intent(self, order: TradeOrder) -> LiveOrderIntent:
        """Create an auditable immutable live-order intent."""

        return LiveOrderIntent(
            order=order,
            idempotency_key=self.create_idempotency_key(order),
            created_at=self._current_time(),
        )

    def evaluate(self, intent: LiveOrderIntent) -> LiveOrderBoundaryResult:
        """Revalidate and reserve an intent, then stop at the locked boundary."""

        evaluated_at = self._current_time()

        # Phase 6-A Step 3: explicit emergency-stop gates run before Kill Switch,
        # risk revalidation, and idempotency reservation. Existing callers that
        # do not yet wire this provider remain compatible while the immutable
        # static lock still guarantees that no live order can be transmitted.
        safety_snapshot = (
            self.safety_snapshot_provider()
            if self.safety_snapshot_provider is not None
            else None
        )
        if safety_snapshot is not None:
            if safety_snapshot.safe_stop_active:
                return LiveOrderBoundaryResult(
                    intent=intent,
                    decision=LiveOrderDecision.BLOCKED,
                    reason=LiveOrderBlockReason.SAFE_STOP,
                    evaluated_at=evaluated_at,
                    risk_assessment=None,
                    kill_switch_evaluation=None,
                    safety_snapshot=safety_snapshot,
                    message="Live order blocked because Safe Stop is active.",
                )

            if not safety_snapshot.reconciliation_consistent:
                return LiveOrderBoundaryResult(
                    intent=intent,
                    decision=LiveOrderDecision.BLOCKED,
                    reason=LiveOrderBlockReason.RECONCILIATION,
                    evaluated_at=evaluated_at,
                    risk_assessment=None,
                    kill_switch_evaluation=None,
                    safety_snapshot=safety_snapshot,
                    message=(
                        "Live order blocked by three-way reconciliation: "
                        f"{safety_snapshot.reconciliation_state}"
                    ),
                )

        # Kill Switch always wins over risk logic, including risk-reducing orders.
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
                safety_snapshot=safety_snapshot,
                message=(
                    "Live order blocked by Kill Switch: "
                    f"{kill_evaluation.reason.value}"
                ),
            )

        # Re-read the latest portfolio immediately at the live boundary.
        signal = self._signal_from_order(
            intent.order,
            evaluated_at=evaluated_at,
        )
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
                safety_snapshot=safety_snapshot,
                message=(
                    "Live order blocked by final risk revalidation: "
                    f"{risk_assessment.reason.value}"
                ),
            )

        fingerprint = self.create_order_fingerprint(intent.order)
        try:
            newly_reserved = self.idempotency_store.reserve(
                intent.idempotency_key,
                order_fingerprint=fingerprint,
                order_id=intent.order.order_id,
                signal_id=intent.order.signal_id,
            )
        except LiveOrderIdempotencyConflictError:
            return LiveOrderBoundaryResult(
                intent=intent,
                decision=LiveOrderDecision.BLOCKED,
                reason=LiveOrderBlockReason.IDEMPOTENCY_CONFLICT,
                evaluated_at=evaluated_at,
                risk_assessment=risk_assessment,
                kill_switch_evaluation=kill_evaluation,
                safety_snapshot=safety_snapshot,
                message="Live-order idempotency conflict blocked.",
            )

        if not newly_reserved:
            return LiveOrderBoundaryResult(
                intent=intent,
                decision=LiveOrderDecision.DUPLICATE,
                reason=LiveOrderBlockReason.DUPLICATE,
                evaluated_at=evaluated_at,
                risk_assessment=risk_assessment,
                kill_switch_evaluation=kill_evaluation,
                safety_snapshot=safety_snapshot,
                message="Duplicate live-order intent blocked.",
            )

        # Preserve the Phase 6-A public safety invariant: the compile-time/static
        # lock is the primary final boundary. Risk and idempotency have already
        # been revalidated above, so this does not bypass those checks.
        if not LIVE_ORDER_TRANSMISSION_ENABLED:
            return LiveOrderBoundaryResult(
                intent=intent,
                decision=LiveOrderDecision.LOCKED,
                reason=LiveOrderBlockReason.STATIC_LOCK,
                evaluated_at=evaluated_at,
                risk_assessment=risk_assessment,
                kill_switch_evaluation=kill_evaluation,
                safety_snapshot=safety_snapshot,
                message="Live order transmission is statically locked in Phase 6-A.",
            )

        # Defense in depth for a future phase: even if the static constant were
        # deliberately changed, runtime arming would still be required.
        if not self.runtime_armed:
            return LiveOrderBoundaryResult(
                intent=intent,
                decision=LiveOrderDecision.LOCKED,
                reason=LiveOrderBlockReason.RUNTIME_LOCK,
                evaluated_at=evaluated_at,
                risk_assessment=risk_assessment,
                kill_switch_evaluation=kill_evaluation,
                safety_snapshot=safety_snapshot,
                message="Live order transmission is not armed at runtime.",
            )

        # Defense in depth: Phase 6-A has no transport even if the constant is
        # accidentally changed later without redesigning this adapter.
        return LiveOrderBoundaryResult(
            intent=intent,
            decision=LiveOrderDecision.LOCKED,
            reason=LiveOrderBlockReason.NO_TRANSPORT,
            evaluated_at=evaluated_at,
            risk_assessment=risk_assessment,
            kill_switch_evaluation=kill_evaluation,
            safety_snapshot=safety_snapshot,
            message="Phase 6-A has no live-order transport.",
        )

    def _signal_from_order(
        self,
        order: TradeOrder,
        *,
        evaluated_at: datetime,
    ) -> TradeSignal:
        """Build the existing risk-manager input from the live order."""

        action = (
            SignalAction.BUY
            if order.side is OrderSide.BUY
            else SignalAction.SELL
        )

        signal_price = self._risk_price(order)

        return TradeSignal(
            signal_id=order.signal_id,
            code=order.code,
            strategy_name="live_order_boundary",
            action=action,
            generated_at=evaluated_at,
            signal_price=signal_price,
            quantity=order.quantity,
            reason="Final live-order boundary risk revalidation.",
            metadata={
                "order_id": order.order_id,
                "order_type": order.order_type.value,
                "live_boundary": True,
            },
        )

    def _risk_price(self, order: TradeOrder) -> float:
        """Resolve a positive current price for final risk revalidation."""

        if order.limit_price is not None:
            return float(order.limit_price)
        if order.stop_price is not None:
            return float(order.stop_price)

        if self.market_price_provider is None:
            raise ValueError(
                "Final live risk revalidation for a MARKET order requires "
                "market_price_provider."
            )

        price = float(self.market_price_provider(order.code))
        if price <= 0:
            raise ValueError(
                "market_price_provider must return a positive price."
            )
        return price

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)
