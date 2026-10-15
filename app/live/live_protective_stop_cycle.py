"""Evaluate durable Live protective stops against authoritative positions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.live.live_protective_exit_execution_flow import (
    LiveProtectiveExitExecutionDecision,
    LiveProtectiveExitExecutionFlow,
    LiveProtectiveExitExecutionResult,
)
from app.live.live_execution_tracking_flow import LiveExecutionTrackingDecision
from app.live.live_protective_exit_service import LiveProtectiveExitDecision
from app.trading.order_models import OrderSide, OrderType, TradeOrder
from app.live.live_protective_stop_repository import (
    LiveProtectiveStopRecord,
    LiveProtectiveStopState,
    SQLiteLiveProtectiveStopRepository,
)


@dataclass(frozen=True, slots=True)
class LiveProtectiveStopCycleResult:
    evaluated: int
    submitted: int
    retired: int
    blocked: int
    results: tuple[LiveProtectiveExitExecutionResult, ...]


class LiveProtectiveStopCycle:
    """Run one fail-closed protective-stop pass.

    ACTIVE rows may submit at most once.  After submission they become
    EXIT_PENDING, so later cycles never resubmit the same protective exit.
    EXIT_PENDING rows are read-only checked until the authoritative account
    confirms that the position is gone, then retired.
    """

    def __init__(
        self,
        *,
        repository: SQLiteLiveProtectiveStopRepository,
        execution_flow: LiveProtectiveExitExecutionFlow,
    ) -> None:
        self.repository = repository
        self.execution_flow = execution_flow

    def __call__(self, trading_date: date) -> LiveProtectiveStopCycleResult:
        results: list[LiveProtectiveExitExecutionResult] = []
        submitted = retired = blocked = 0
        records = self.repository.list_current()

        for record in records:
            if record.state is LiveProtectiveStopState.EXIT_PENDING:
                # Always ask the authoritative position service first.  This
                # lets migrated legacy pending rows retire safely when flat.
                plan = self.execution_flow.exit_service.evaluate_stop_loss(
                    code=record.code,
                    stop_price=record.stop_price,
                    trading_date=trading_date,
                )
                if plan.decision is LiveProtectiveExitDecision.NO_POSITION:
                    self.repository.retire(
                        entry_execution_key=record.entry_execution_key
                    )
                    retired += 1
                    continue
                if plan.decision is LiveProtectiveExitDecision.BLOCKED:
                    blocked += 1
                    continue

                # Old rows can legitimately have no durable exit identity.
                # If a real position still exists, such a row is unresolved:
                # never resubmit and never allow new risk.
                if not record.exit_execution_key or not record.exit_order_id:
                    blocked += 1
                    continue

                order = TradeOrder(
                    order_id=record.exit_order_id,
                    signal_id=record.exit_execution_key,
                    code=record.code,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=record.quantity,
                )
                try:
                    tracking = self.execution_flow.reconcile(
                        execution_key=record.exit_execution_key,
                        order=order,
                    )
                except Exception:
                    blocked += 1
                    continue

                # A working/partially-filled SELL may remain pending. Any
                # terminal/unknown/mismatched lifecycle while a position still
                # exists is unresolved protection and blocks all new risk.
                if tracking.decision not in {
                    LiveExecutionTrackingDecision.WORKING_CONSISTENT,
                    LiveExecutionTrackingDecision.PARTIALLY_FILLED_CONSISTENT,
                }:
                    blocked += 1
                continue

            result = self.execution_flow.submit_stop_loss(
                code=record.code,
                stop_price=record.stop_price,
                trading_date=trading_date,
            )
            results.append(result)
            if result.decision is LiveProtectiveExitExecutionDecision.SUBMISSION_STARTED:
                # The real LiveProtectiveExitExecutionResult always carries
                # execution_key + plan.order.  getattr keeps the older isolated
                # unit-test seam compatible; identity-less pending is fail-
                # closed on the next cycle if a position still exists.
                execution_key = getattr(result, "execution_key", None)
                plan_order = getattr(result.plan, "order", None)
                exit_order_id = (
                    getattr(plan_order, "order_id", None)
                    if plan_order is not None else None
                )
                self.repository.mark_exit_pending(
                    entry_execution_key=record.entry_execution_key,
                    exit_execution_key=execution_key,
                    exit_order_id=exit_order_id,
                )
                submitted += 1
            elif result.decision is LiveProtectiveExitExecutionDecision.BLOCKED:
                blocked += 1
            elif (
                result.plan.decision
                is LiveProtectiveExitDecision.NO_POSITION
            ):
                self.repository.retire(
                    entry_execution_key=record.entry_execution_key
                )
                retired += 1

        return LiveProtectiveStopCycleResult(
            evaluated=len(records),
            submitted=submitted,
            retired=retired,
            blocked=blocked,
            results=tuple(results),
        )
