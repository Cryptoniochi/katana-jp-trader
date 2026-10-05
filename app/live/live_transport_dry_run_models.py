"""Phase 6-D Step 6A models for non-transmitting Live transport dry-runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.live.live_broker_transport_models import LiveTransportRequest
from app.live.live_execution_journal_models import LiveExecutionJournalRecord
from app.live.live_submission_boundary_models import LiveSubmissionBoundaryResult


class SimulatedLiveTransportDecision(StrEnum):
    """Outcome of a simulated broker-transport evaluation."""

    SIMULATED_ACCEPTED = "simulated_accepted"


@dataclass(frozen=True, slots=True)
class SimulatedLiveTransportResult:
    """Auditable proof that an order reached simulation but not a broker."""

    request: LiveTransportRequest
    decision: SimulatedLiveTransportDecision
    evaluated_at: datetime
    simulated_broker_order_id: str
    message: str

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware.")
        if not self.simulated_broker_order_id.strip():
            raise ValueError("simulated_broker_order_id must not be empty.")
        if not self.message.strip():
            raise ValueError("message must not be empty.")


class DryRunSubmissionDecision(StrEnum):
    """Outcome of one dry-run submission-coordination attempt."""

    SIMULATED_TRANSPORT_REACHED = "simulated_transport_reached"


@dataclass(frozen=True, slots=True)
class DryRunSubmissionResult:
    """Result of the durable dry-run path.

    The journal deliberately remains SUBMISSION_PENDING in the dedicated dry-run
    database.  It is never marked SUBMITTED because no broker accepted an order.
    """

    decision: DryRunSubmissionDecision
    evaluated_at: datetime
    journal_record: LiveExecutionJournalRecord
    submission_boundary_result: LiveSubmissionBoundaryResult
    transport_result: SimulatedLiveTransportResult
    message: str

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware.")
        if not self.message.strip():
            raise ValueError("message must not be empty.")
