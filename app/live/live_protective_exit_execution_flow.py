"""Phase 5B: connect real-account protective exits to durable live tracking.

This module does not enable Live mode, arm the runtime, or unlock transport.
A planned SELL is allowed to reach the tracking flow only when the fresh
pre-submission broker position still equals the quantity used for planning.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol

from app.live.live_execution_tracking_flow import LiveExecutionTrackingResult
from app.live.live_protective_exit_service import (
    LiveEndOfDayExitBatch,
    LiveProtectiveExitDecision,
    LiveProtectiveExitPlan,
    LiveProtectiveExitService,
)
from app.trading.order_models import OrderSide, TradeOrder


class LiveProtectiveExitExecutionDecision(StrEnum):
    NO_ACTION = "no_action"
    BLOCKED = "blocked"
    SUBMISSION_STARTED = "submission_started"


@dataclass(frozen=True, slots=True)
class LiveProtectiveExitExecutionResult:
    decision: LiveProtectiveExitExecutionDecision
    plan: LiveProtectiveExitPlan
    execution_key: str | None
    tracking: LiveExecutionTrackingResult | None

    @property
    def may_retry_same_order(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class LiveEndOfDayExecutionBatch:
    plan_batch: LiveEndOfDayExitBatch
    results: tuple[LiveProtectiveExitExecutionResult, ...]

    @property
    def is_blocked(self) -> bool:
        return self.plan_batch.is_blocked or any(
            item.decision is LiveProtectiveExitExecutionDecision.BLOCKED
            for item in self.results
        )


class _TrackingFlow(Protocol):
    def submit(
        self, *, execution_key: str, order: TradeOrder, trading_date: date,
        required_baseline_quantity: int | None = None,
    ) -> LiveExecutionTrackingResult: ...
    def reconcile(
        self, *, execution_key: str, order: TradeOrder
    ) -> LiveExecutionTrackingResult: ...


class LiveProtectiveExitExecutionFlow:
    def __init__(
        self, *, exit_service: LiveProtectiveExitService, tracking_flow: _TrackingFlow
    ) -> None:
        self.exit_service = exit_service
        self.tracking_flow = tracking_flow

    def submit_stop_loss(
        self, *, code: str, stop_price: float, trading_date: date
    ) -> LiveProtectiveExitExecutionResult:
        plan = self.exit_service.evaluate_stop_loss(
            code=code, stop_price=stop_price, trading_date=trading_date
        )
        return self._submit_plan(plan=plan, trading_date=trading_date)

    def submit_end_of_day(self, *, trading_date: date) -> LiveEndOfDayExecutionBatch:
        batch = self.exit_service.plan_end_of_day(trading_date=trading_date)
        if batch.is_blocked:
            return LiveEndOfDayExecutionBatch(plan_batch=batch, results=tuple())
        results = []
        for plan in batch.plans:
            result = self._submit_plan(plan=plan, trading_date=trading_date)
            results.append(result)
            if result.decision is LiveProtectiveExitExecutionDecision.BLOCKED:
                break
        return LiveEndOfDayExecutionBatch(plan_batch=batch, results=tuple(results))

    def reconcile(
        self, *, execution_key: str, order: TradeOrder
    ) -> LiveExecutionTrackingResult:
        if order.side is not OrderSide.SELL:
            raise ValueError("protective exit reconciliation requires a SELL order")
        return self.tracking_flow.reconcile(
            execution_key=execution_key, order=order
        )

    def _submit_plan(
        self, *, plan: LiveProtectiveExitPlan, trading_date: date
    ) -> LiveProtectiveExitExecutionResult:
        if plan.decision is LiveProtectiveExitDecision.BLOCKED:
            return LiveProtectiveExitExecutionResult(
                LiveProtectiveExitExecutionDecision.BLOCKED, plan, None, None
            )
        if plan.decision is not LiveProtectiveExitDecision.EXIT_REQUIRED:
            return LiveProtectiveExitExecutionResult(
                LiveProtectiveExitExecutionDecision.NO_ACTION, plan, None, None
            )
        order = plan.order
        if order is None or order.side is not OrderSide.SELL:
            raise RuntimeError("EXIT_REQUIRED plan must contain a SELL order")
        execution_key = f"protective-exit:{order.order_id}"
        try:
            tracking = self.tracking_flow.submit(
                execution_key=execution_key,
                order=order,
                trading_date=trading_date,
                required_baseline_quantity=plan.quantity,
            )
        except Exception:
            return LiveProtectiveExitExecutionResult(
                LiveProtectiveExitExecutionDecision.BLOCKED,
                plan, execution_key, None,
            )
        return LiveProtectiveExitExecutionResult(
            LiveProtectiveExitExecutionDecision.SUBMISSION_STARTED,
            plan, execution_key, tracking,
        )
