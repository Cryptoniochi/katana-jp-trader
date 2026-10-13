"""Phase 5: live-account protective exit planning boundary.

This module is intentionally read-only with respect to broker transport.
It treats the fresh live account snapshot as the source of truth, builds
SELL/MARKET exit orders only for actual cash long positions, and never sends
an order itself.

Safety invariants:
- PaperBroker state is never consulted.
- A fresh, complete live account snapshot is required.
- Exit quantity is derived from the broker position, never caller input.
- Duplicate position rows for one symbol are aggregated.
- Protective-stop evaluation fails closed when market price is unavailable.
- End-of-day liquidation plans every actual live position.
- This module contains no sendorder/submission/transport capability.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any, Protocol

from app.trading.order_models import OrderSide, OrderType, TradeOrder


class LiveProtectiveExitReason(StrEnum):
    STOP_LOSS = "stop_loss"
    END_OF_DAY = "end_of_day"


class LiveProtectiveExitDecision(StrEnum):
    NO_POSITION = "no_position"
    HOLD = "hold"
    EXIT_REQUIRED = "exit_required"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class LiveProtectiveExitPlan:
    decision: LiveProtectiveExitDecision
    reason: LiveProtectiveExitReason
    evaluated_at: datetime
    code: str | None
    quantity: int
    market_price: float | None
    trigger_price: float | None
    order: TradeOrder | None
    message: str

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware.")
        if self.quantity < 0:
            raise ValueError("quantity must not be negative.")
        if not self.message.strip():
            raise ValueError("message must not be empty.")
        if self.decision is LiveProtectiveExitDecision.EXIT_REQUIRED:
            if self.order is None:
                raise ValueError("EXIT_REQUIRED requires an order.")
            if self.order.side is not OrderSide.SELL:
                raise ValueError("Protective exit order must be SELL.")
            if self.order.order_type is not OrderType.MARKET:
                raise ValueError("Protective exit order must be MARKET.")
            if self.order.quantity != self.quantity:
                raise ValueError("Exit quantity must match the live position.")
        elif self.order is not None:
            raise ValueError("Only EXIT_REQUIRED may contain an order.")


@dataclass(frozen=True, slots=True)
class LiveEndOfDayExitBatch:
    evaluated_at: datetime
    trading_date: date
    plans: tuple[LiveProtectiveExitPlan, ...]

    @property
    def exit_orders(self) -> tuple[TradeOrder, ...]:
        return tuple(
            plan.order
            for plan in self.plans
            if plan.decision is LiveProtectiveExitDecision.EXIT_REQUIRED
            and plan.order is not None
        )

    @property
    def is_blocked(self) -> bool:
        return any(
            plan.decision is LiveProtectiveExitDecision.BLOCKED
            for plan in self.plans
        )


class LiveAccountStateProvider(Protocol):
    def refresh(self) -> Any: ...


MarketPriceProvider = Callable[[str], float]
NowProvider = Callable[[], datetime]


class LiveProtectiveExitService:
    """Build safe exit intentions from real broker positions only."""

    def __init__(
        self,
        *,
        account_state_provider: LiveAccountStateProvider | Callable[[], Any],
        market_price_provider: MarketPriceProvider,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.account_state_provider = account_state_provider
        self.market_price_provider = market_price_provider
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def evaluate_stop_loss(
        self,
        *,
        code: str,
        stop_price: float,
        trading_date: date,
    ) -> LiveProtectiveExitPlan:
        normalized = self._code(code)
        if stop_price <= 0:
            raise ValueError("stop_price must be greater than zero.")
        now = self._now()
        try:
            snapshot = self._snapshot()
            quantity = self._position_quantities(snapshot).get(normalized, 0)
        except Exception as error:
            return self._blocked(
                reason=LiveProtectiveExitReason.STOP_LOSS,
                now=now,
                code=normalized,
                trigger_price=float(stop_price),
                message=f"Live account position retrieval failed: {error}",
            )

        if quantity <= 0:
            return LiveProtectiveExitPlan(
                decision=LiveProtectiveExitDecision.NO_POSITION,
                reason=LiveProtectiveExitReason.STOP_LOSS,
                evaluated_at=now,
                code=normalized,
                quantity=0,
                market_price=None,
                trigger_price=float(stop_price),
                order=None,
                message="No actual live position exists for the symbol.",
            )

        try:
            market_price = float(self.market_price_provider(normalized))
            if market_price <= 0:
                raise ValueError("market price must be positive")
        except Exception as error:
            return self._blocked(
                reason=LiveProtectiveExitReason.STOP_LOSS,
                now=now,
                code=normalized,
                quantity=quantity,
                trigger_price=float(stop_price),
                message=f"Market price retrieval failed: {error}",
            )

        if market_price > stop_price:
            return LiveProtectiveExitPlan(
                decision=LiveProtectiveExitDecision.HOLD,
                reason=LiveProtectiveExitReason.STOP_LOSS,
                evaluated_at=now,
                code=normalized,
                quantity=quantity,
                market_price=market_price,
                trigger_price=float(stop_price),
                order=None,
                message="Protective stop has not been reached.",
            )

        return self._exit_plan(
            reason=LiveProtectiveExitReason.STOP_LOSS,
            now=now,
            trading_date=trading_date,
            code=normalized,
            quantity=quantity,
            market_price=market_price,
            trigger_price=float(stop_price),
        )

    def plan_end_of_day(
        self,
        *,
        trading_date: date,
    ) -> LiveEndOfDayExitBatch:
        now = self._now()
        try:
            snapshot = self._snapshot()
            quantities = self._position_quantities(snapshot)
        except Exception as error:
            blocked = self._blocked(
                reason=LiveProtectiveExitReason.END_OF_DAY,
                now=now,
                code=None,
                message=f"Live account position retrieval failed: {error}",
            )
            return LiveEndOfDayExitBatch(
                evaluated_at=now,
                trading_date=trading_date,
                plans=(blocked,),
            )

        plans = tuple(
            self._exit_plan(
                reason=LiveProtectiveExitReason.END_OF_DAY,
                now=now,
                trading_date=trading_date,
                code=code,
                quantity=quantity,
                market_price=None,
                trigger_price=None,
            )
            for code, quantity in sorted(quantities.items())
            if quantity > 0
        )
        return LiveEndOfDayExitBatch(
            evaluated_at=now,
            trading_date=trading_date,
            plans=plans,
        )

    def _exit_plan(
        self,
        *,
        reason: LiveProtectiveExitReason,
        now: datetime,
        trading_date: date,
        code: str,
        quantity: int,
        market_price: float | None,
        trigger_price: float | None,
    ) -> LiveProtectiveExitPlan:
        stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        tag = "stop" if reason is LiveProtectiveExitReason.STOP_LOSS else "eod"
        order = TradeOrder(
            order_id=f"live-exit-{tag}-{code}-{stamp}",
            signal_id=f"live-exit-{tag}-{code}-{trading_date.isoformat()}-{stamp}",
            code=code,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=quantity,
        )
        return LiveProtectiveExitPlan(
            decision=LiveProtectiveExitDecision.EXIT_REQUIRED,
            reason=reason,
            evaluated_at=now,
            code=code,
            quantity=quantity,
            market_price=market_price,
            trigger_price=trigger_price,
            order=order,
            message=(
                "Actual live position requires protective exit."
                if reason is LiveProtectiveExitReason.STOP_LOSS
                else "Actual live position requires end-of-day liquidation."
            ),
        )

    def _snapshot(self) -> Any:
        provider = self.account_state_provider
        if callable(provider):
            snapshot = provider()
        elif hasattr(provider, "refresh"):
            snapshot = provider.refresh()
        elif hasattr(provider, "snapshot"):
            snapshot = provider.snapshot()
        else:
            raise RuntimeError("live account state provider has no refresh method")
        self._require_fresh_complete(snapshot)
        return snapshot

    @staticmethod
    def _require_fresh_complete(snapshot: Any) -> None:
        if snapshot is None:
            raise RuntimeError("live account snapshot is missing")

        for name in ("is_complete", "complete", "is_valid"):
            if hasattr(snapshot, name) and getattr(snapshot, name) is False:
                raise RuntimeError(f"live account snapshot {name}=False")

        for name in ("is_stale", "stale"):
            if hasattr(snapshot, name) and getattr(snapshot, name) is True:
                raise RuntimeError(f"live account snapshot {name}=True")

        error = getattr(snapshot, "error", None)
        if error:
            raise RuntimeError(f"live account snapshot error={error}")

    @classmethod
    def _position_quantities(cls, snapshot: Any) -> dict[str, int]:
        positions = getattr(snapshot, "positions", None)
        if positions is None and isinstance(snapshot, dict):
            positions = snapshot.get("positions")
        if positions is None:
            raise RuntimeError("live account snapshot has no positions")

        quantities: dict[str, int] = {}
        for position in positions:
            code = cls._position_value(position, "code", "symbol", "Symbol")
            quantity = cls._position_value(
                position, "quantity", "qty", "LeavesQty", "leaves_qty"
            )
            normalized = cls._code(str(code))
            try:
                numeric = float(quantity)
            except (TypeError, ValueError) as error:
                raise RuntimeError(
                    f"invalid live position quantity for {normalized}: {quantity!r}"
                ) from error
            if numeric < 0 or not numeric.is_integer():
                raise RuntimeError(
                    f"invalid live position quantity for {normalized}: {quantity!r}"
                )
            quantities[normalized] = quantities.get(normalized, 0) + int(numeric)
        return quantities

    @staticmethod
    def _position_value(position: Any, *names: str) -> Any:
        for name in names:
            if isinstance(position, dict) and name in position:
                return position[name]
            if hasattr(position, name):
                return getattr(position, name)
        raise RuntimeError(f"live position is missing {names[0]}")

    @staticmethod
    def _code(code: str) -> str:
        normalized = code.strip()
        if not normalized.isdigit() or len(normalized) not in {4, 5}:
            raise ValueError("code must be a 4- or 5-digit symbol.")
        return normalized

    def _now(self) -> datetime:
        now = self.now_provider()
        if now.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return now.astimezone(timezone.utc)

    @staticmethod
    def _blocked(
        *,
        reason: LiveProtectiveExitReason,
        now: datetime,
        code: str | None,
        message: str,
        quantity: int = 0,
        trigger_price: float | None = None,
    ) -> LiveProtectiveExitPlan:
        return LiveProtectiveExitPlan(
            decision=LiveProtectiveExitDecision.BLOCKED,
            reason=reason,
            evaluated_at=now,
            code=code,
            quantity=quantity,
            market_price=None,
            trigger_price=trigger_price,
            order=None,
            message=message,
        )
