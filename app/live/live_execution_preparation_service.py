"""Phase 6-B preparation coordinator for locked live execution.

This module deliberately has no broker adapter, network transport, order-send
method, or claim operation.  It only connects the already-locked Phase 6-A
boundary to the durable Phase 6-B execution journal.

A valid duplicate boundary result is intentionally allowed to repair the
crash window between durable idempotency reservation and journal PREPARED
creation.  The journal's immutable-content checks keep that recovery path
safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.live.live_execution_journal_models import (
    LiveExecutionJournalRecord,
    LiveExecutionState,
)
from app.live.live_execution_journal_repository import (
    SQLiteLiveExecutionJournal,
)
from app.live.live_order_adapter import LockedLiveOrderAdapter
from app.live.live_order_models import (
    LiveOrderBoundaryResult,
    LiveOrderDecision,
    LiveOrderIntent,
)


class LiveOrderBoundary(Protocol):
    """Minimal Phase 6-A boundary contract required for preparation."""

    def evaluate(self, intent: LiveOrderIntent) -> LiveOrderBoundaryResult:
        """Evaluate an immutable live-order intent."""


@dataclass(frozen=True, slots=True)
class LiveExecutionPreparationResult:
    """Auditable result of boundary evaluation plus journal preparation."""

    boundary_result: LiveOrderBoundaryResult
    journal_record: LiveExecutionJournalRecord | None
    newly_prepared: bool

    @property
    def is_prepared(self) -> bool:
        return (
            self.journal_record is not None
            and self.journal_record.state is LiveExecutionState.PREPARED
        )


class LockedLiveExecutionPreparationService:
    """Prepare only boundary-approved intents, while keeping execution locked."""

    def __init__(
        self,
        *,
        boundary: LiveOrderBoundary,
        journal: SQLiteLiveExecutionJournal,
    ) -> None:
        self.boundary = boundary
        self.journal = journal

    def prepare(
        self,
        intent: LiveOrderIntent,
    ) -> LiveExecutionPreparationResult:
        """Evaluate the live boundary and durably converge to PREPARED.

        BLOCKED results never create journal state.

        LOCKED means safety/risk/idempotency checks passed and Phase 6-A's
        transmission lock stopped progress.

        DUPLICATE is also eligible for PREPARED repair because the Phase 6-A
        boundary only returns DUPLICATE after the same safety/risk checks pass
        and the immutable idempotency reservation is already present.  This
        closes the crash window where reservation committed but journal
        creation did not.

        This service never CLAIMS, never marks submission pending, and never
        submits an order.
        """

        boundary_result = self.boundary.evaluate(intent)

        if boundary_result.decision is LiveOrderDecision.BLOCKED:
            return LiveExecutionPreparationResult(
                boundary_result=boundary_result,
                journal_record=None,
                newly_prepared=False,
            )

        if boundary_result.decision not in {
            LiveOrderDecision.LOCKED,
            LiveOrderDecision.DUPLICATE,
        }:
            raise RuntimeError(
                "Unsupported live-order boundary decision: "
                f"{boundary_result.decision!r}"
            )

        order = intent.order
        fingerprint = LockedLiveOrderAdapter.create_order_fingerprint(order)
        existing = self.journal.get(intent.idempotency_key)

        self.journal.prepare(
            execution_key=intent.idempotency_key,
            order_fingerprint=fingerprint,
            order_id=order.order_id,
            signal_id=order.signal_id,
        )

        record = self.journal.get_required(intent.idempotency_key)
        return LiveExecutionPreparationResult(
            boundary_result=boundary_result,
            journal_record=record,
            newly_prepared=existing is None,
        )
