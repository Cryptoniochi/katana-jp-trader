"""Bridge realtime strategy signals into the final Live execution flow.

The bridge is deliberately broker-independent on the signal side and contains
no PaperBroker dependency.  New entries are BUY-only; position exits remain the
responsibility of the authoritative Live protective-exit path.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from datetime import date
from typing import Protocol

from app.live.live_production_runner import LiveEntryIntent
from app.market.realtime_signal_models import RealtimeSignalProcessResult
from app.trading.order_models import OrderSide, OrderType, TradeOrder
from app.trading.signal_models import SignalAction, TradeSignal


class LiveSignalBridgeError(RuntimeError):
    """Raised when a strategy signal cannot safely enter the Live path."""


class RealtimeSignalEngineLike(Protocol):
    def process(self, prices: Iterable[object]) -> RealtimeSignalProcessResult:
        """Evaluate newly collected market bars."""


class PreparedTrackingFlowLike(Protocol):
    def submit(
        self,
        *,
        execution_key: str,
        order: TradeOrder,
        trading_date: date,
        required_baseline_quantity: int | None = None,
    ) -> object:
        """Run risk/safety -> PREPARED -> CLAIMED -> tracked submission."""


class LiveRealtimeSignalIntentProvider:
    """Convert RealtimeSignalEngine BUY signals into Live entry intents.

    SELL/EXIT signals are intentionally rejected rather than silently routed as
    entries.  Live exits must use the authoritative protective-exit lifecycle.
    """

    def __init__(
        self,
        *,
        signal_engine: RealtimeSignalEngineLike,
        price_provider: Callable[[], Iterable[object]],
    ) -> None:
        self.signal_engine = signal_engine
        self.price_provider = price_provider
        self.last_result: RealtimeSignalProcessResult | None = None

    def __call__(self) -> tuple[LiveEntryIntent, ...]:
        result = self.signal_engine.process(tuple(self.price_provider()))
        self.last_result = result
        intents: list[LiveEntryIntent] = []
        seen_execution_keys: set[str] = set()

        for signal in result.signals:
            if signal.action is not SignalAction.BUY:
                raise LiveSignalBridgeError(
                    "Realtime Live entry bridge received a non-BUY signal; "
                    "SELL/EXIT must use the Live protective-exit path. "
                    f"signal_id={signal.signal_id} action={signal.action.value}"
                )
            if signal.signal_id in seen_execution_keys:
                raise LiveSignalBridgeError(
                    "Duplicate execution key produced in one Live cycle. "
                    f"signal_id={signal.signal_id}"
                )
            seen_execution_keys.add(signal.signal_id)
            intents.append(_signal_to_entry_intent(signal))

        return tuple(intents)


def _signal_to_entry_intent(signal: TradeSignal) -> LiveEntryIntent:
    return LiveEntryIntent(
        execution_key=signal.signal_id,
        code=signal.code,
        quantity=signal.quantity,
        side="BUY",
    )


class FinalLiveEntrySubmitter:
    """Submit normalized Live entry intents through FinalLiveRuntime only.

    The generated order is deterministic and market-only.  A required baseline
    of zero prevents a stale/new BUY intent from adding to an already existing
    real position for the same symbol.  Risk, daily-loss, Kill Switch, safety,
    idempotency, PREPARED and CLAIMED checks remain owned by the injected final
    prepared tracking flow.
    """

    def __init__(
        self,
        *,
        prepared_tracking_flow: PreparedTrackingFlowLike,
        reconciliation_registry=None,
    ) -> None:
        self.prepared_tracking_flow = prepared_tracking_flow
        self.reconciliation_registry = reconciliation_registry

    def __call__(self, intent: LiveEntryIntent, trading_date: date) -> object:
        order = self._to_trade_order(intent)
        # Persist recovery identity before any path can reach broker transport.
        if self.reconciliation_registry is not None:
            self.reconciliation_registry.prepare(
                execution_key=intent.execution_key,
                trading_date=trading_date,
                order=order,
            )
        return self.prepared_tracking_flow.submit(
            execution_key=intent.execution_key,
            order=order,
            trading_date=trading_date,
            required_baseline_quantity=0,
        )

    @staticmethod
    def _to_trade_order(intent: LiveEntryIntent) -> TradeOrder:
        if intent.side.upper() != "BUY":
            raise LiveSignalBridgeError("Live entry submitter permits BUY only.")
        digest = hashlib.sha256(
            intent.execution_key.encode("utf-8")
        ).hexdigest()[:24]
        return TradeOrder(
            order_id=f"live-{digest}",
            signal_id=intent.execution_key,
            code=intent.code,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=intent.quantity,
        )
