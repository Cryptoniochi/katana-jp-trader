"""Persistence boundary for completed fault-tolerance attempts.

Phase 6-D Step 6C-F deliberately does not execute FaultToleranceService.
It only accepts an attempt that has already been computed by the owning
production fault-tolerance runtime and persists that exact completed result.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.live.live_fault_tolerance_saved_state import SavedFaultToleranceState
from app.live.live_fault_tolerance_saved_state_writer import FaultToleranceSavedStateWriter
from app.supervisor.fault_tolerance_models import FaultToleranceAttempt


@dataclass(frozen=True, slots=True)
class FaultTolerancePersistenceResult:
    attempt: FaultToleranceAttempt
    saved_state: SavedFaultToleranceState


class FaultToleranceAttemptPersistenceBoundary:
    """Persist an already-computed FaultToleranceAttempt and nothing else."""

    def __init__(self, *, writer: FaultToleranceSavedStateWriter) -> None:
        self.writer = writer

    def persist(
        self,
        attempt: FaultToleranceAttempt,
    ) -> FaultTolerancePersistenceResult:
        if not isinstance(attempt, FaultToleranceAttempt):
            raise TypeError("attempt must be a FaultToleranceAttempt")
        saved_state = self.writer.write_attempt(attempt)
        return FaultTolerancePersistenceResult(
            attempt=attempt,
            saved_state=saved_state,
        )
