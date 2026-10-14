"""Evaluate durable Live protective stops against authoritative positions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.live.live_protective_exit_execution_flow import (
    LiveProtectiveExitExecutionDecision,
    LiveProtectiveExitExecutionFlow,
    LiveProtectiveExitExecutionResult,
)
from app.live.live_protective_exit_service import LiveProtectiveExitDecision
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
                elif plan.decision is LiveProtectiveExitDecision.BLOCKED:
                    blocked += 1
                # HOLD/EXIT_REQUIRED while pending means the broker position
                # still exists.  Never submit again; await reconciliation.
                continue

            result = self.execution_flow.submit_stop_loss(
                code=record.code,
                stop_price=record.stop_price,
                trading_date=trading_date,
            )
            results.append(result)
            if result.decision is LiveProtectiveExitExecutionDecision.SUBMISSION_STARTED:
                self.repository.mark_exit_pending(
                    entry_execution_key=record.entry_execution_key
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
