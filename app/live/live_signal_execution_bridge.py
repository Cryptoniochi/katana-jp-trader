"""Bridge realtime strategy signals into the final Live execution flow.

The realtime engine is evaluated exactly once per Live cycle. BUY signals are
returned as Live entry intents. SELL/EXIT signals are retained for the
authoritative strategy-exit cycle; they are never submitted as entries.
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
    """Evaluate realtime strategies once and split BUY from SELL/EXIT safely.

    BUY signals become LiveEntryIntent objects. SELL/EXIT signals are retained
    in last_exit_signals for the strategy-exit cycle. Unknown actions fail
    closed. The provider never submits an order itself.
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
        self.last_exit_signals: tuple[TradeSignal, ...] = tuple()

    def __call__(self) -> tuple[LiveEntryIntent, ...]:
        result = self.signal_engine.process(tuple(self.price_provider()))
        self.last_result = result
        intents: list[LiveEntryIntent] = []
        exits: list[TradeSignal] = []
        seen_execution_keys: set[str] = set()

        for signal in result.signals:
            if signal.signal_id in seen_execution_keys:
                raise LiveSignalBridgeError(
                    "Duplicate execution key produced in one Live cycle. "
                    f"signal_id={signal.signal_id}"
                )
            seen_execution_keys.add(signal.signal_id)

            if signal.action is SignalAction.BUY:
                intents.append(_signal_to_entry_intent(signal))
            elif signal.action in {SignalAction.SELL, SignalAction.EXIT}:
                exits.append(signal)
            else:
                raise LiveSignalBridgeError(
                    "Realtime Live signal bridge received an unsupported action. "
                    f"signal_id={signal.signal_id} action={signal.action}"
                )

        self.last_exit_signals = tuple(exits)
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

    A normal final risk rejection is an order-level BLOCK, not a runtime
    failure.  Such a rejection therefore returns False so LiveProductionRunner
    can continue operating and report the entry as blocked.

    Unexpected preparation/claim/journal/broker failures are deliberately not
    swallowed: they continue to propagate and fail closed.

    The generated order is deterministic and market-only. A required baseline
    of zero prevents a stale/new BUY intent from adding to an already existing
    real position for the same symbol.
    """

    _NORMAL_RISK_BLOCK_PREFIX = (
        "Live execution preparation was blocked; submission is prohibited. "
        "reason=risk_revalidation "
    )

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

        try:
            return self.prepared_tracking_flow.submit(
                execution_key=intent.execution_key,
                order=order,
                trading_date=trading_date,
                required_baseline_quantity=0,
            )
        except RuntimeError as exc:
            # Final risk revalidation is expected to reject some otherwise valid
            # strategy signals (position value, exposure, cash, daily loss, etc.).
            # That is an order-level decision and must not crash the Live runtime.
            #
            # All other RuntimeError paths remain fail-closed.
            if str(exc).startswith(self._NORMAL_RISK_BLOCK_PREFIX):
                return False
            raise

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
