"""Read-only lifecycle boundary for broker-submitted live executions.

This layer connects the durable KATANA SUBMITTED journal state to broker-side
execution reconciliation.  It never submits, cancels, replaces, or retries an
order.  The durable journal remains the submission/idempotency authority while
kabu Station remains the execution/fill authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.live.live_execution_journal_models import (
    LiveExecutionJournalRecord,
    LiveExecutionState,
)
from app.live.live_execution_journal_repository import (
    LiveExecutionTransitionError,
    SQLiteLiveExecutionJournal,
)
from app.live.live_execution_reconciliation import (
    LiveExecutionReconciliation,
    LiveExecutionReconciliationService,
    LiveExecutionReconciliationState,
)


class LiveSubmittedExecutionDecision(StrEnum):
    WORKING = "working"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    TERMINATED_UNFILLED = "terminated_unfilled"
    TERMINATED_PARTIAL = "terminated_partial"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LiveSubmittedExecutionResult:
    execution_key: str
    decision: LiveSubmittedExecutionDecision
    journal_record: LiveExecutionJournalRecord
    reconciliation: LiveExecutionReconciliation
    message: str

    @property
    def may_retry_submission(self) -> bool:
        """This lifecycle never authorizes resubmission of a submitted order."""
        return False

    @property
    def is_fully_filled(self) -> bool:
        return self.decision is LiveSubmittedExecutionDecision.FILLED


class _ReconciliationService(Protocol):
    def reconcile(self, broker_order_id: str) -> LiveExecutionReconciliation: ...


class LiveSubmittedExecutionLifecycle:
    """Reconcile a durable SUBMITTED execution against the real broker order."""

    _DECISION_BY_STATE = {
        LiveExecutionReconciliationState.ACCEPTED: LiveSubmittedExecutionDecision.WORKING,
        LiveExecutionReconciliationState.PARTIALLY_FILLED: LiveSubmittedExecutionDecision.PARTIALLY_FILLED,
        LiveExecutionReconciliationState.FILLED: LiveSubmittedExecutionDecision.FILLED,
        LiveExecutionReconciliationState.TERMINATED_UNFILLED: LiveSubmittedExecutionDecision.TERMINATED_UNFILLED,
        LiveExecutionReconciliationState.TERMINATED_PARTIAL: LiveSubmittedExecutionDecision.TERMINATED_PARTIAL,
        LiveExecutionReconciliationState.UNKNOWN: LiveSubmittedExecutionDecision.UNKNOWN,
    }

    def __init__(
        self,
        *,
        journal: SQLiteLiveExecutionJournal,
        reconciliation_service: _ReconciliationService,
    ) -> None:
        self.journal = journal
        self.reconciliation_service = reconciliation_service

    def reconcile(self, execution_key: str) -> LiveSubmittedExecutionResult:
        key = str(execution_key or "").strip()
        if not key:
            raise ValueError("execution_key is required")

        record = self.journal.get_required(key)
        if record.state is not LiveExecutionState.SUBMITTED:
            raise LiveExecutionTransitionError(
                "Only a durable SUBMITTED live execution may be broker-reconciled."
            )
        broker_order_id = str(record.broker_order_id or "").strip()
        if not broker_order_id:
            raise LiveExecutionTransitionError(
                "SUBMITTED live execution has no broker_order_id."
            )

        reconciliation = self.reconciliation_service.reconcile(broker_order_id)
        if reconciliation.broker_order_id != broker_order_id:
            raise RuntimeError("Reconciliation returned a different broker OrderId.")

        decision = self._DECISION_BY_STATE[reconciliation.state]
        # Deliberately do not mutate SUBMITTED here.  The existing journal is the
        # durable submission/idempotency ledger and has no fill-state transitions.
        # Broker execution truth is returned separately and can be consumed by the
        # future real-account position/runtime layer.
        after = self.journal.get_required(key)
        if after != record:
            raise LiveExecutionTransitionError(
                "Read-only broker reconciliation changed the execution journal."
            )

        return LiveSubmittedExecutionResult(
            execution_key=key,
            decision=decision,
            journal_record=after,
            reconciliation=reconciliation,
            message=self._message(decision),
        )

    @staticmethod
    def _message(decision: LiveSubmittedExecutionDecision) -> str:
        messages = {
            LiveSubmittedExecutionDecision.WORKING: "Broker accepted order; execution is still working.",
            LiveSubmittedExecutionDecision.PARTIALLY_FILLED: "Broker confirms a partial execution; no resubmission is permitted.",
            LiveSubmittedExecutionDecision.FILLED: "Broker confirms the submitted order is fully filled.",
            LiveSubmittedExecutionDecision.TERMINATED_UNFILLED: "Broker order terminated without execution; this lifecycle does not authorize retry.",
            LiveSubmittedExecutionDecision.TERMINATED_PARTIAL: "Broker order terminated after partial execution; this lifecycle does not authorize retry.",
            LiveSubmittedExecutionDecision.UNKNOWN: "Broker execution state is unknown; fail closed and do not retry submission.",
        }
        return messages[decision]
