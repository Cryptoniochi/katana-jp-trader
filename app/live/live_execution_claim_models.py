"""Phase 6-B claim-gate models for durable live execution.

These models describe only ownership acquisition of an already PREPARED
execution.  They contain no broker transport or submission capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.live.live_execution_journal_models import LiveExecutionJournalRecord
from app.live.live_order_safety import LiveOrderSafetySnapshot
from app.risk.kill_switch_models import KillSwitchEvaluation


class LiveExecutionClaimDecision(StrEnum):
    """Result of attempting to acquire a PREPARED live execution."""

    CLAIMED = "claimed"
    BLOCKED = "blocked"


class LiveExecutionClaimBlockReason(StrEnum):
    """Fail-closed reason why ownership was not acquired."""

    SAFETY_STATE_UNAVAILABLE = "safety_state_unavailable"
    SAFE_STOP = "safe_stop"
    RECONCILIATION = "reconciliation"
    KILL_SWITCH_STATE_UNAVAILABLE = "kill_switch_state_unavailable"
    KILL_SWITCH = "kill_switch"


@dataclass(frozen=True, slots=True)
class LiveExecutionClaimResult:
    """Auditable outcome of the Phase 6-B claim gate."""

    decision: LiveExecutionClaimDecision
    evaluated_at: datetime
    journal_record: LiveExecutionJournalRecord
    block_reason: LiveExecutionClaimBlockReason | None = None
    safety_snapshot: LiveOrderSafetySnapshot | None = None
    kill_switch_evaluation: KillSwitchEvaluation | None = None
    message: str = ""

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware.")
        if not self.message.strip():
            raise ValueError("message must not be empty.")

        if self.decision is LiveExecutionClaimDecision.CLAIMED:
            if self.block_reason is not None:
                raise ValueError("CLAIMED result must not have block_reason.")
        elif self.block_reason is None:
            raise ValueError("BLOCKED result requires block_reason.")

    @property
    def is_claimed(self) -> bool:
        return self.decision is LiveExecutionClaimDecision.CLAIMED

    @property
    def is_blocked(self) -> bool:
        return self.decision is LiveExecutionClaimDecision.BLOCKED
