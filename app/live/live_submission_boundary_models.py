"""Phase 6-B submission-boundary models.

These models describe entry into the durable SUBMISSION_PENDING state and
recovery of ambiguous pending attempts.  They provide no broker transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.live.live_execution_journal_models import LiveExecutionJournalRecord


class LiveSubmissionBoundaryDecision(StrEnum):
    """Outcome of entering or recovering the pre-transport boundary."""

    SUBMISSION_PENDING = "submission_pending"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LiveSubmissionBoundaryResult:
    """Auditable result of a Phase 6-B submission-boundary operation."""

    decision: LiveSubmissionBoundaryDecision
    evaluated_at: datetime
    journal_record: LiveExecutionJournalRecord
    message: str

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware.")
        if not self.message.strip():
            raise ValueError("message must not be empty.")

    @property
    def is_submission_pending(self) -> bool:
        return (
            self.decision
            is LiveSubmissionBoundaryDecision.SUBMISSION_PENDING
        )

    @property
    def is_unknown(self) -> bool:
        return self.decision is LiveSubmissionBoundaryDecision.UNKNOWN
