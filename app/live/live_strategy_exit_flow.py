"""Authoritative Live execution path for realtime strategy SELL/EXIT signals.

This module never trusts strategy quantity as the broker position source of
truth. A strategy exit may sell only a position whose KATANA ownership is
durably proven by the current protective-stop record. Broker-visible quantity
must exactly equal that owned quantity immediately before submission.

Existing unfinished SELL orders are never cancelled or duplicated. Existing
BUY conflicts use the already-proven EOD conflict resolver, which durably
cancels BUY risk and re-plans from a fresh broker position.

After a submitted or submission-unknown SELL, the protective-stop row is moved
to EXIT_PENDING with deterministic execution/order identity. The existing
protective-stop reconciliation cycle then owns restart-safe reconciliation.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol, Sequence

from app.live.live_execution_tracking_flow import LiveExecutionTrackingDecision
from app.live.live_protective_exit_conflict_resolver import (
    LiveProtectiveExitConflictResolver,
)
from app.live.live_protective_stop_repository import (
    LiveProtectiveStopState,
    SQLiteLiveProtectiveStopRepository,
)
from app.trading.order_models import OrderSide, OrderType, TradeOrder
from app.trading.signal_models import SignalAction, TradeSignal


class LiveStrategyExitDecision(StrEnum):
    NO_ACTION = "no_action"
    SUBMISSION_STARTED = "submission_started"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class LiveStrategyExitResult:
    decision: LiveStrategyExitDecision
    signal_id: str
    code: str
    execution_key: str | None = None
    order_id: str | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class LiveStrategyExitCycleResult:
    evaluated: int
    submitted: int
    no_action: int
    blocked: int
    results: tuple[LiveStrategyExitResult, ...]


class PreparedTrackingFlowLike(Protocol):
    def submit(
        self,
        *,
        execution_key: str,
        order: TradeOrder,
        trading_date: date,
        required_baseline_quantity: int | None = None,
    ) -> object: ...


class ExitSignalSource(Protocol):
    last_exit_signals: Sequence[TradeSignal]


class LiveStrategyExitFlow:
    """Submit one strategy exit through existing Live safety/tracking layers."""

    def __init__(
        self,
        *,
        ownership_repository: SQLiteLiveProtectiveStopRepository,
        conflict_resolver: LiveProtectiveExitConflictResolver,
        prepared_tracking_flow: PreparedTrackingFlowLike,
    ) -> None:
        self.ownership_repository = ownership_repository
        self.conflict_resolver = conflict_resolver
        self.prepared_tracking_flow = prepared_tracking_flow

    def submit_signal(
        self, signal: TradeSignal, *, trading_date: date
    ) -> LiveStrategyExitResult:
        if signal.action not in {SignalAction.SELL, SignalAction.EXIT}:
            raise ValueError("Live strategy exit requires SELL or EXIT signal.")

        code = str(signal.code).strip()
        record = self.ownership_repository.get_current(code)

        # A strategy can believe it owns a position before a Live BUY is filled.
        # No durable ownership means KATANA must not sell anything.
        if record is None:
            return LiveStrategyExitResult(
                LiveStrategyExitDecision.NO_ACTION,
                signal.signal_id,
                code,
                message="No current KATANA-owned Live position exists.",
            )

        if record.state is LiveProtectiveStopState.EXIT_PENDING:
            return LiveStrategyExitResult(
                LiveStrategyExitDecision.BLOCKED,
                signal.signal_id,
                code,
                execution_key=record.exit_execution_key,
                order_id=record.exit_order_id,
                message="A Live exit is already pending for this KATANA-owned position.",
            )

        if record.state is not LiveProtectiveStopState.ACTIVE:
            return LiveStrategyExitResult(
                LiveStrategyExitDecision.BLOCKED,
                signal.signal_id,
                code,
                message=f"Unexpected ownership state: {record.state.value}.",
            )

        # Reuse the proven conflict semantics: never cancel an unfinished SELL;
        # cancel unfinished BUY risk durably, then re-read the actual position.
        resolution = self.conflict_resolver.resolve_eod(
            code=code,
            trading_date=trading_date,
        )
        plan = resolution.plan
        if plan is None or plan.order is None:
            return LiveStrategyExitResult(
                LiveStrategyExitDecision.BLOCKED,
                signal.signal_id,
                code,
                message=f"Strategy exit conflict resolution blocked: {resolution.message}",
            )

        broker_quantity = int(plan.order.quantity)
        owned_quantity = int(record.quantity)
        if broker_quantity != owned_quantity:
            return LiveStrategyExitResult(
                LiveStrategyExitDecision.BLOCKED,
                signal.signal_id,
                code,
                message=(
                    "KATANA ownership quantity mismatch for strategy exit: "
                    f"broker={broker_quantity}, owned={owned_quantity}."
                ),
            )

        execution_key = f"strategy-exit:{signal.signal_id}"
        digest = hashlib.sha256(execution_key.encode("utf-8")).hexdigest()[:24]
        order = TradeOrder(
            order_id=f"live-strategy-exit-{digest}",
            signal_id=signal.signal_id,
            code=code,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=owned_quantity,
        )

        try:
            tracking = self.prepared_tracking_flow.submit(
                execution_key=execution_key,
                order=order,
                trading_date=trading_date,
                required_baseline_quantity=owned_quantity,
            )
        except Exception as error:
            return LiveStrategyExitResult(
                LiveStrategyExitDecision.BLOCKED,
                signal.signal_id,
                code,
                execution_key=execution_key,
                order_id=order.order_id,
                message=f"Strategy exit submission blocked: {type(error).__name__}: {error}",
            )

        decision = getattr(tracking, "decision", None)
        if decision not in {
            LiveExecutionTrackingDecision.SUBMITTED,
            LiveExecutionTrackingDecision.SUBMISSION_UNKNOWN,
        }:
            return LiveStrategyExitResult(
                LiveStrategyExitDecision.BLOCKED,
                signal.signal_id,
                code,
                execution_key=execution_key,
                order_id=order.order_id,
                message=f"Strategy exit was not submitted; tracking decision={decision}.",
            )

        # UNKNOWN is deliberately treated as pending: never retry an order whose
        # broker acceptance is uncertain.
        self.ownership_repository.mark_exit_pending(
            entry_execution_key=record.entry_execution_key,
            exit_execution_key=execution_key,
            exit_order_id=order.order_id,
        )
        return LiveStrategyExitResult(
            LiveStrategyExitDecision.SUBMISSION_STARTED,
            signal.signal_id,
            code,
            execution_key=execution_key,
            order_id=order.order_id,
            message="Strategy exit submission started and ownership is EXIT_PENDING.",
        )


class LiveStrategyExitCycle:
    """Consume exits produced by the already-evaluated realtime signal provider."""

    def __init__(
        self,
        *,
        signal_source: ExitSignalSource,
        flow: LiveStrategyExitFlow,
    ) -> None:
        self.signal_source = signal_source
        self.flow = flow

    def __call__(self, trading_date: date) -> LiveStrategyExitCycleResult:
        signals = tuple(self.signal_source.last_exit_signals)
        results: list[LiveStrategyExitResult] = []
        submitted = no_action = blocked = 0

        for signal in signals:
            result = self.flow.submit_signal(signal, trading_date=trading_date)
            results.append(result)
            if result.decision is LiveStrategyExitDecision.SUBMISSION_STARTED:
                submitted += 1
            elif result.decision is LiveStrategyExitDecision.NO_ACTION:
                no_action += 1
            else:
                blocked += 1

        return LiveStrategyExitCycleResult(
            evaluated=len(signals),
            submitted=submitted,
            no_action=no_action,
            blocked=blocked,
            results=tuple(results),
        )
