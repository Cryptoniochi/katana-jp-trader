"""Production reconciliation cycle for durable Live BUY executions."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from app.live.live_confirmed_entry_stop_recorder import (
    LiveConfirmedEntryStopDecision,
    LiveConfirmedEntryStopRecorder,
)
from app.live.live_entry_reconciliation_registry import (
    SQLiteLiveEntryReconciliationRegistry,
)
from app.live.live_execution_tracking_flow import (
    LiveExecutionTrackingDecision,
    LiveExecutionTrackingFlow,
)
from app.live.live_execution_journal_models import LiveExecutionState


LOGGER = logging.getLogger("katana")


@dataclass(frozen=True, slots=True)
class LiveEntryReconciliationCycleResult:
    evaluated: int
    completed: int
    stops_recorded: int
    blocked: int


class LiveEntryReconciliationCycle:
    """Reconcile all durable pending entries before protection/new risk."""

    _TERMINAL = {
        LiveExecutionTrackingDecision.FILLED_CONSISTENT,
        LiveExecutionTrackingDecision.TERMINATED_CONSISTENT,
    }

    def __init__(
        self,
        *,
        registry: SQLiteLiveEntryReconciliationRegistry,
        tracking_flow: LiveExecutionTrackingFlow,
        stop_recorder: LiveConfirmedEntryStopRecorder,
        journal,
    ) -> None:
        self.registry = registry
        self.tracking_flow = tracking_flow
        self.stop_recorder = stop_recorder
        self.journal = journal

    @staticmethod
    def _is_prior_day_external_close(
        *,
        row,
        trading_date: date,
        tracking,
    ) -> bool:
        """Return True only when a prior-day KATANA BUY is already externally flat.

        This is deliberately narrow. A submitted BUY may be retired without
        creating a protective stop only when broker reconciliation proves that
        the original BUY had a positive terminal execution and the authoritative
        current position has returned exactly to the durable pre-submission
        baseline.

        Same-day mismatches remain fail-closed because broker position reporting
        can briefly lag immediately after a fill.
        """
        if row.trading_date >= trading_date:
            return False

        if tracking.decision is not LiveExecutionTrackingDecision.POSITION_MISMATCH:
            return False

        lifecycle = tracking.lifecycle
        consistency = tracking.consistency

        if lifecycle is None or consistency is None:
            return False

        reconciliation = lifecycle.reconciliation
        if not reconciliation.is_terminal:
            return False

        executed_quantity = consistency.executed_quantity
        if executed_quantity is None or executed_quantity <= 0:
            return False

        if executed_quantity > row.quantity:
            return False

        actual_quantity = consistency.actual_quantity
        baseline_quantity = consistency.baseline_quantity

        if actual_quantity is None:
            return False

        return actual_quantity == baseline_quantity

    def __call__(self, trading_date: date) -> LiveEntryReconciliationCycleResult:
        completed = recorded = blocked = 0
        rows = self.registry.list_pending()

        for row in rows:
            journal_record = self.journal.get(row.execution_key)

            # The registry reservation is intentionally created before boundary
            # preparation. If no journal record exists, execution never reached
            # PREPARED and therefore cannot have reached CLAIMED/SUBMITTED or the
            # broker transport.
            if journal_record is None:
                self.registry.complete(row.execution_key)
                completed += 1
                continue

            # A broker-explicit rejection is persisted as ABORTED: no broker
            # OrderId exists and automatic retry is prohibited.
            if journal_record.state is LiveExecutionState.ABORTED:
                self.registry.complete(row.execution_key)
                completed += 1
                continue

            # PREPARED/CLAIMED/SUBMISSION_PENDING/UNKNOWN remain fail-closed.
            if journal_record.state is not LiveExecutionState.SUBMITTED:
                blocked += 1
                continue

            try:
                tracking = self.tracking_flow.reconcile(
                    execution_key=row.execution_key,
                    order=row.to_order(),
                )

                # Recovery for a prior-day entry that was subsequently closed
                # outside KATANA (for example, a verified manual broker SELL).
                #
                # The original broker BUY must be terminal and positively
                # executed, while the current authoritative position must have
                # returned exactly to the pre-submission baseline. There is no
                # remaining KATANA-created exposure to protect, so the durable
                # registry item can be completed without creating a stale stop.
                if self._is_prior_day_external_close(
                    row=row,
                    trading_date=trading_date,
                    tracking=tracking,
                ):
                    self.registry.complete(row.execution_key)
                    completed += 1
                    continue

                stop = self.stop_recorder.record(
                    execution_key=row.execution_key,
                    order=row.to_order(),
                    trading_date=row.trading_date,
                    tracking_result=tracking,
                )
            except Exception:
                LOGGER.exception(
                    "Live entry reconciliation failed: "
                    "execution_key=%s code=%s entry_trading_date=%s "
                    "reconciliation_trading_date=%s",
                    row.execution_key,
                    getattr(row, "code", None)
                    or getattr(row.to_order(), "code", None),
                    row.trading_date,
                    trading_date,
                )
                blocked += 1
                continue

            if stop.decision is LiveConfirmedEntryStopDecision.BLOCKED:
                blocked += 1
                continue

            if stop.decision is LiveConfirmedEntryStopDecision.RECORDED:
                recorded += 1

            if tracking.decision in self._TERMINAL:
                # Terminated-unfilled has no stop and is safe to complete;
                # terminated-partial/fill must already have produced a stop.
                if (
                    tracking.lifecycle is not None
                    and tracking.lifecycle.reconciliation.cumulative_quantity
                    and stop.decision
                    is not LiveConfirmedEntryStopDecision.RECORDED
                ):
                    blocked += 1
                    continue

                self.registry.complete(row.execution_key)
                completed += 1

            elif tracking.decision in {
                LiveExecutionTrackingDecision.UNKNOWN,
                LiveExecutionTrackingDecision.POSITION_MISMATCH,
            }:
                blocked += 1

        return LiveEntryReconciliationCycleResult(
            evaluated=len(rows),
            completed=completed,
            stops_recorded=recorded,
            blocked=blocked,
        )
