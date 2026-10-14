"""Resolve broker-order conflicts for live protective exits."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.live.live_exit_order_conflict_service import LiveExitOrderConflictService
from app.live.live_protective_cancel_service import LiveProtectiveCancelService
from app.live.live_protective_exit_service import (
    LiveProtectiveExitDecision,
    LiveProtectiveExitPlan,
    LiveProtectiveExitService,
)


class LiveConflictResolutionDecision(StrEnum):
    CLEAR = "clear"
    REPLANNED = "replanned"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class LiveConflictResolutionResult:
    decision: LiveConflictResolutionDecision
    plan: LiveProtectiveExitPlan | None
    message: str

    @property
    def can_submit(self) -> bool:
        return (
            self.plan is not None
            and self.plan.decision is LiveProtectiveExitDecision.EXIT_REQUIRED
            and self.decision is not LiveConflictResolutionDecision.BLOCKED
        )


class LiveProtectiveExitConflictResolver:
    def __init__(
        self,
        *,
        conflict_service: LiveExitOrderConflictService,
        cancel_service: LiveProtectiveCancelService,
        exit_service: LiveProtectiveExitService,
    ) -> None:
        self.conflict_service = conflict_service
        self.cancel_service = cancel_service
        self.exit_service = exit_service

    def resolve_stop_loss(
        self, *, code: str, stop_price: float, trading_date
    ) -> LiveConflictResolutionResult:
        return self._resolve(
            code=code,
            replan=lambda: self.exit_service.evaluate_stop_loss(
                code=code, stop_price=stop_price, trading_date=trading_date
            ),
        )

    def resolve_eod(
        self, *, code: str, trading_date
    ) -> LiveConflictResolutionResult:
        """Resolve EOD conflicts without ever cancelling an unfinished SELL.

        An unfinished SELL may itself be a previously submitted protective/EOD
        liquidation.  Cancelling it merely because the live position has not yet
        reflected an asynchronous fill can create cancel/replace churn and duplicate
        exit risk.  EOD therefore fails closed while any unfinished SELL exists.

        Unfinished BUY orders are still cancelled through the existing durable
        cancellation path before a fresh live-position replan.
        """
        first = self.conflict_service.check(code=code)
        if first.is_clear:
            return LiveConflictResolutionResult(
                LiveConflictResolutionDecision.CLEAR,
                self.exit_service.evaluate_eod_position(
                    code=code, trading_date=trading_date
                ),
                "No cancellation required.",
            )
        if not first.conflicts:
            return LiveConflictResolutionResult(
                LiveConflictResolutionDecision.BLOCKED,
                None,
                "Broker order state is unavailable or ambiguous.",
            )

        # Side "1" is SELL in kabu Station.  Never cancel an unfinished SELL
        # from the EOD path: it may be the liquidation already in flight.
        if any(conflict.side == "1" for conflict in first.conflicts):
            return LiveConflictResolutionResult(
                LiveConflictResolutionDecision.BLOCKED,
                None,
                "Unfinished SELL exists for EOD symbol; leave it in place and "
                "wait for broker reconciliation before any new liquidation.",
            )

        # Only BUY conflicts remain.  These may increase exposure and must be
        # durably cancelled before the position is replanned.
        for conflict in first.conflicts:
            cancelled = self.cancel_service.cancel_and_reconcile(
                broker_order_id=conflict.broker_order_id
            )
            if not cancelled.is_cancelled:
                return LiveConflictResolutionResult(
                    LiveConflictResolutionDecision.BLOCKED,
                    None,
                    cancelled.message,
                )
        second = self.conflict_service.check(code=code)
        if not second.is_clear:
            return LiveConflictResolutionResult(
                LiveConflictResolutionDecision.BLOCKED,
                None,
                "Broker conflict remains after cancellation.",
            )
        return LiveConflictResolutionResult(
            LiveConflictResolutionDecision.REPLANNED,
            self.exit_service.evaluate_eod_position(
                code=code, trading_date=trading_date
            ),
            "BUY conflicts cancelled; replanned from fresh live position.",
        )

    def _resolve(self, *, code: str, replan) -> LiveConflictResolutionResult:
        first = self.conflict_service.check(code=code)
        if first.is_clear:
            return LiveConflictResolutionResult(
                LiveConflictResolutionDecision.CLEAR,
                replan(),
                "No cancellation required.",
            )
        if not first.conflicts:
            return LiveConflictResolutionResult(
                LiveConflictResolutionDecision.BLOCKED,
                None,
                "Broker order state is unavailable or ambiguous.",
            )
        for conflict in first.conflicts:
            cancelled = self.cancel_service.cancel_and_reconcile(
                broker_order_id=conflict.broker_order_id
            )
            if not cancelled.is_cancelled:
                return LiveConflictResolutionResult(
                    LiveConflictResolutionDecision.BLOCKED,
                    None,
                    cancelled.message,
                )
        second = self.conflict_service.check(code=code)
        if not second.is_clear:
            return LiveConflictResolutionResult(
                LiveConflictResolutionDecision.BLOCKED,
                None,
                "Broker conflict remains after cancellation.",
            )
        return LiveConflictResolutionResult(
            LiveConflictResolutionDecision.REPLANNED,
            replan(),
            "Conflicts cancelled; replanned from fresh live position.",
        )
