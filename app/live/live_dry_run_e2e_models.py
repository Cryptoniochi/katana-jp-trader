"""Phase 6-D Step 6B end-to-end Live dry-run result models.

These models describe a network-free rehearsal only.  They do not represent
broker acceptance and cannot mark an execution SUBMITTED.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.live.final_live_readiness import FinalLiveReadinessReport
from app.live.live_execution_claim_models import LiveExecutionClaimResult
from app.live.live_execution_preparation_service import (
    LiveExecutionPreparationResult,
)
from app.live.live_transport_dry_run_models import DryRunSubmissionResult


class LiveDryRunE2EDecision(StrEnum):
    """Terminal outcome of one end-to-end dry-run attempt."""

    BLOCKED_READINESS = "blocked_readiness"
    BLOCKED_PREPARATION = "blocked_preparation"
    BLOCKED_CLAIM = "blocked_claim"
    SIMULATED_TRANSPORT_REACHED = "simulated_transport_reached"


@dataclass(frozen=True, slots=True)
class LiveDryRunE2EResult:
    """Auditable aggregate result for one network-free dry-run."""

    decision: LiveDryRunE2EDecision
    evaluated_at: datetime
    readiness_report: FinalLiveReadinessReport
    preparation_result: LiveExecutionPreparationResult | None
    claim_result: LiveExecutionClaimResult | None
    submission_result: DryRunSubmissionResult | None
    message: str

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware.")
        if not self.message.strip():
            raise ValueError("message must not be empty.")

    @property
    def simulated_transport_reached(self) -> bool:
        return (
            self.decision
            is LiveDryRunE2EDecision.SIMULATED_TRANSPORT_REACHED
        )
