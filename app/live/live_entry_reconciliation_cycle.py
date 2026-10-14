"""Production reconciliation cycle for durable Live BUY executions."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date

from app.live.live_confirmed_entry_stop_recorder import (
    LiveConfirmedEntryStopDecision,
    LiveConfirmedEntryStopRecorder,
)
from app.live.live_entry_reconciliation_registry import SQLiteLiveEntryReconciliationRegistry
from app.live.live_execution_tracking_flow import (
    LiveExecutionTrackingDecision,
    LiveExecutionTrackingFlow,
)
from app.live.live_execution_journal_models import LiveExecutionState


@dataclass(frozen=True,slots=True)
class LiveEntryReconciliationCycleResult:
    evaluated:int
    completed:int
    stops_recorded:int
    blocked:int


class LiveEntryReconciliationCycle:
    """Reconcile all durable pending entries before protection/new risk."""

    _TERMINAL={
        LiveExecutionTrackingDecision.FILLED_CONSISTENT,
        LiveExecutionTrackingDecision.TERMINATED_CONSISTENT,
    }

    def __init__(self,*,registry:SQLiteLiveEntryReconciliationRegistry,
                 tracking_flow:LiveExecutionTrackingFlow,
                 stop_recorder:LiveConfirmedEntryStopRecorder,
                 journal) -> None:
        self.registry=registry
        self.tracking_flow=tracking_flow
        self.stop_recorder=stop_recorder
        self.journal=journal

    def __call__(self,trading_date:date) -> LiveEntryReconciliationCycleResult:
        completed=recorded=blocked=0
        rows=self.registry.list_pending()
        for row in rows:
            journal_record=self.journal.get(row.execution_key)
            # PREPARED/CLAIMED means submission has not durably reached SUBMITTED.
            # Keep it pending and block new risk; never guess/retry here.
            if journal_record is None or journal_record.state is not LiveExecutionState.SUBMITTED:
                blocked+=1
                continue
            try:
                tracking=self.tracking_flow.reconcile(
                    execution_key=row.execution_key,order=row.to_order())
                stop=self.stop_recorder.record(
                    execution_key=row.execution_key,order=row.to_order(),
                    trading_date=row.trading_date,tracking_result=tracking)
            except Exception:
                blocked+=1
                continue

            if stop.decision is LiveConfirmedEntryStopDecision.BLOCKED:
                blocked+=1
                continue
            if stop.decision is LiveConfirmedEntryStopDecision.RECORDED:
                recorded+=1
            if tracking.decision in self._TERMINAL:
                # Terminated-unfilled has no stop and is safe to complete;
                # terminated-partial/fill must already have produced a stop.
                if (tracking.lifecycle is not None
                    and tracking.lifecycle.reconciliation.cumulative_quantity
                    and stop.decision is not LiveConfirmedEntryStopDecision.RECORDED):
                    blocked+=1
                    continue
                self.registry.complete(row.execution_key)
                completed+=1
            elif tracking.decision in {
                LiveExecutionTrackingDecision.UNKNOWN,
                LiveExecutionTrackingDecision.POSITION_MISMATCH,
            }:
                blocked+=1
        return LiveEntryReconciliationCycleResult(
            evaluated=len(rows),completed=completed,stops_recorded=recorded,blocked=blocked)
