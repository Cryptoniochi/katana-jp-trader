"""Cancel protective-exit conflicts, then replan from fresh live position."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from app.live.live_exit_order_conflict_service import LiveExitOrderConflictService
from app.live.live_protective_cancel_service import LiveProtectiveCancelService
from app.live.live_protective_exit_service import LiveProtectiveExitDecision,LiveProtectiveExitPlan,LiveProtectiveExitService

class LiveConflictResolutionDecision(StrEnum):
    CLEAR="clear"
    REPLANNED="replanned"
    BLOCKED="blocked"

@dataclass(frozen=True, slots=True)
class LiveConflictResolutionResult:
    decision:LiveConflictResolutionDecision
    plan:LiveProtectiveExitPlan|None
    message:str
    @property
    def can_submit(self)->bool:
        return self.plan is not None and self.plan.decision is LiveProtectiveExitDecision.EXIT_REQUIRED and self.decision is not LiveConflictResolutionDecision.BLOCKED

class LiveProtectiveExitConflictResolver:
    def __init__(self,*,conflict_service:LiveExitOrderConflictService,cancel_service:LiveProtectiveCancelService,exit_service:LiveProtectiveExitService)->None:
        self.conflict_service=conflict_service
        self.cancel_service=cancel_service
        self.exit_service=exit_service

    def resolve_stop_loss(self,*,code:str,stop_price:float,trading_date)->LiveConflictResolutionResult:
        first=self.conflict_service.check(code=code)
        if first.is_clear:
            plan=self.exit_service.evaluate_stop_loss(code=code,stop_price=stop_price,trading_date=trading_date)
            return LiveConflictResolutionResult(LiveConflictResolutionDecision.CLEAR,plan,"No cancellation required.")
        if not first.conflicts:
            return LiveConflictResolutionResult(LiveConflictResolutionDecision.BLOCKED,None,"Broker order state is unavailable or ambiguous.")
        for conflict in first.conflicts:
            cancelled=self.cancel_service.cancel_and_reconcile(broker_order_id=conflict.broker_order_id)
            if not cancelled.is_cancelled:
                return LiveConflictResolutionResult(LiveConflictResolutionDecision.BLOCKED,None,cancelled.message)
        second=self.conflict_service.check(code=code)
        if not second.is_clear:
            return LiveConflictResolutionResult(LiveConflictResolutionDecision.BLOCKED,None,"Broker conflict remains after cancellation.")
        # evaluate_stop_loss refreshes actual account state: old planned quantity is discarded.
        plan=self.exit_service.evaluate_stop_loss(code=code,stop_price=stop_price,trading_date=trading_date)
        return LiveConflictResolutionResult(LiveConflictResolutionDecision.REPLANNED,plan,"Conflicts cancelled; replanned from fresh live position.")
