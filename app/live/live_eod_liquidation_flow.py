"""Bounded Live EOD liquidation with final authoritative flat verification."""
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
    """Liquidate actual Live positions and prove the account is flat.

    COMPLETE is returned only after a fresh authoritative account read is flat.
    Once this invocation starts an exit for a symbol, a later non-flat read never
    submits that symbol again.  Real fills are asynchronous, so the safe response
    is BLOCKED/pending reconciliation rather than cancel/replace churn.
    """

    def __init__(
        self,
        *,
        exit_service: LiveProtectiveExitService,
        conflict_resolver: LiveProtectiveExitConflictResolver,
        execution_flow: LiveProtectiveExitExecutionFlow,
        max_passes: int = 3,
    ) -> None:
        if isinstance(max_passes, bool) or max_passes < 1:
            raise ValueError("max_passes must be a positive integer")
        self.exit_service = exit_service
        self.conflict_resolver = conflict_resolver
        self.execution_flow = execution_flow
        self.max_passes = int(max_passes)

    def submit_all(self, *, trading_date) -> LiveEodExecutionResult:
        results: list[LiveProtectiveExitExecutionResult] = []
        submitted_symbols: set[str] = set()

        for pass_number in range(1, self.max_passes + 1):
            try:
                plans = self.exit_service.plan_end_of_day(
                    trading_date=trading_date
                ).plans
            except Exception as exc:
                return LiveEodExecutionResult(
                    LiveEodExecutionDecision.BLOCKED,
                    tuple(results),
                    f"EOD flat verification failed on pass {pass_number}: {exc}",
                )

            if not plans:
                return LiveEodExecutionResult(
                    LiveEodExecutionDecision.COMPLETE,
                    tuple(results),
                    "Fresh live account verification confirms all positions are flat.",
                )

            # A symbol submitted earlier in this invocation is still visible in
            # the authoritative position view.  Do not resolve conflicts again:
            # doing so could cancel the still-working EOD SELL and resubmit it.
            pending = sorted(
                {candidate.code for candidate in plans}
                & submitted_symbols
            )
            if pending:
                return LiveEodExecutionResult(
                    LiveEodExecutionDecision.BLOCKED,
                    tuple(results),
                    "EOD exit submission is still awaiting authoritative flat "
                    "confirmation; no cancel or resubmission was attempted. "
                    f"Pending symbols: {','.join(pending)}",
                )

            for candidate in plans:
                resolution = self.conflict_resolver.resolve_eod(
                    code=candidate.code,
                    trading_date=trading_date,
                )
                if resolution.plan is None:
                    return LiveEodExecutionResult(
                        LiveEodExecutionDecision.BLOCKED,
                        tuple(results),
                        f"EOD liquidation blocked for {candidate.code}: "
                        f"{resolution.message}",
                    )

                result = self.execution_flow._submit_plan(
                    plan=resolution.plan,
                    trading_date=trading_date,
                )
                results.append(result)
                if result.decision is LiveProtectiveExitExecutionDecision.BLOCKED:
                    return LiveEodExecutionResult(
                        LiveEodExecutionDecision.BLOCKED,
                        tuple(results),
                        f"EOD liquidation blocked for {candidate.code}.",
                    )
                if (
                    result.decision
                    is LiveProtectiveExitExecutionDecision.SUBMISSION_STARTED
                ):
                    submitted_symbols.add(candidate.code)

        try:
            remaining = self.exit_service.plan_end_of_day(
                trading_date=trading_date
            ).plans
        except Exception as exc:
            return LiveEodExecutionResult(
                LiveEodExecutionDecision.BLOCKED,
                tuple(results),
                f"Final EOD flat verification failed: {exc}",
            )

        if not remaining:
            return LiveEodExecutionResult(
                LiveEodExecutionDecision.COMPLETE,
                tuple(results),
                "Final fresh live account verification confirms all positions are flat.",
            )

        symbols = ",".join(sorted({plan.code for plan in remaining}))
        return LiveEodExecutionResult(
            LiveEodExecutionDecision.BLOCKED,
            tuple(results),
            "EOD liquidation did not reach a verified flat account within "
            f"{self.max_passes} passes. Remaining symbols: {symbols}",
        )
