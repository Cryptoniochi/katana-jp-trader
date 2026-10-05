"""Durable, read-only-safe fault-tolerance state for live safety decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.supervisor.fault_tolerance_models import FaultToleranceDecision


@dataclass(frozen=True, slots=True)
class SavedFaultToleranceState:
    """Minimal durable representation of one completed fault-tolerance attempt."""

    attempt_number: int
    checked_at: datetime
    decision: FaultToleranceDecision
    consecutive_failure_count: int
    message: str

    def __post_init__(self) -> None:
        message = self.message.strip()

        if self.attempt_number <= 0:
            raise ValueError("attempt_number must be greater than zero")
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("checked_at must be timezone-aware")
        if self.consecutive_failure_count < 0:
            raise ValueError(
                "consecutive_failure_count must be zero or greater"
            )
        if not message:
            raise ValueError("message must not be empty")

        object.__setattr__(self, "message", message)
