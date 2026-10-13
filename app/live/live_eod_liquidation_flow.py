"""Live EOD liquidation through the same conflict/cancel/baseline safety path."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.live.live_protective_exit_conflict_resolver import (
    LiveProtectiveExitConflictResolver,
)
from app.live.live_protective_exit_execution_flow import (
    LiveProtectiveExitExecutionDecision,
    LiveProtectiveExitExecutionFlow,
    LiveProtectiveExitExecutionResult,
)
from app.live.live_protective_exit_service import LiveProtectiveExitService


class LiveEodExecutionDecision(StrEnum):
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class LiveEodExecutionResult:
    decision: LiveEodExecutionDecision
    results: tuple[LiveProtectiveExitExecutionResult, ...]
    message: str


class LiveEodLiquidationFlow:
    def __init__(
        self,
        *,
        exit_service: LiveProtectiveExitService,
        conflict_resolver: LiveProtectiveExitConflictResolver,
        execution_flow: LiveProtectiveExitExecutionFlow,
    ) -> None:
        self.exit_service = exit_service
        self.conflict_resolver = conflict_resolver
        self.execution_flow = execution_flow

    def submit_all(self, *, trading_date) -> LiveEodExecutionResult:
        # The service reads actual live positions.  These initial plans are only
        # used to enumerate symbols; every symbol is replanned immediately before
        # submission after broker-order conflict resolution.
        initial = self.exit_service.plan_end_of_day(trading_date=trading_date).plans
        results: list[LiveProtectiveExitExecutionResult] = []

        for candidate in initial:
            resolution = self.conflict_resolver.resolve_eod(
                code=candidate.code, trading_date=trading_date
            )
            if resolution.plan is None:
                return LiveEodExecutionResult(
                    LiveEodExecutionDecision.BLOCKED,
                    tuple(results),
                    f"EOD liquidation blocked for {candidate.code}: {resolution.message}",
                )
            result = self.execution_flow._submit_plan(
                plan=resolution.plan, trading_date=trading_date
            )
            results.append(result)
            if result.decision is LiveProtectiveExitExecutionDecision.BLOCKED:
                return LiveEodExecutionResult(
                    LiveEodExecutionDecision.BLOCKED,
                    tuple(results),
                    f"EOD liquidation blocked for {candidate.code}.",
                )

        return LiveEodExecutionResult(
            LiveEodExecutionDecision.COMPLETE,
            tuple(results),
            "EOD liquidation plans were processed through the live safety path.",
        )
