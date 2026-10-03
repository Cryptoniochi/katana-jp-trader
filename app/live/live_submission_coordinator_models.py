"""Phase 6-C models for the locked live submission coordinator.

These models describe orchestration between the durable submission boundary
and the locked broker transport.  They contain no broker client and perform
no network I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.live.live_broker_transport_models import LiveTransportResult
from app.live.live_execution_journal_models import LiveExecutionJournalRecord
from app.live.live_submission_boundary_models import LiveSubmissionBoundaryResult


class LiveSubmissionCoordinatorDecision(StrEnum):
    """Outcome of one locked submission-coordination attempt."""

    TRANSPORT_LOCKED = "transport_locked"


@dataclass(frozen=True, slots=True)
class LiveSubmissionCoordinatorResult:
    """Auditable result of coordinating the locked submission boundary."""

    decision: LiveSubmissionCoordinatorDecision
    evaluated_at: datetime
    journal_record: LiveExecutionJournalRecord
    submission_boundary_result: LiveSubmissionBoundaryResult
    transport_result: LiveTransportResult
    message: str

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware.")

        message = self.message.strip()
        if not message:
            raise ValueError("message must not be empty.")
        object.__setattr__(self, "message", message)
