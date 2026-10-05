"""Production fault-tolerance execution/persistence boundary.

Phase 6-D Step 6C-G makes ownership explicit without attaching recovery to the
Paper Trading loop or the Live dry-run CLI. The executor invokes an injected
fault-tolerance service exactly once, then persists only the completed attempt.

Construction is inert. No work happens until execute_once() is called by a
future reviewed production owner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.live.live_fault_tolerance_persistence_boundary import (
    FaultToleranceAttemptPersistenceBoundary,
    FaultTolerancePersistenceResult,
)
from app.supervisor.fault_tolerance_models import FaultToleranceAttempt


class FaultToleranceAttemptExecutor(Protocol):
    """Minimal execution contract owned by the fault-tolerance subsystem."""

    def run_once(self) -> FaultToleranceAttempt: ...


@dataclass(frozen=True, slots=True)
class ProductionFaultToleranceExecutionResult:
    """One completed fault-tolerance execution and its durable state."""

    attempt: FaultToleranceAttempt
    persistence: FaultTolerancePersistenceResult


class ProductionFaultToleranceExecutionBoundary:
    """Execute the owning fault-tolerance service once and persist its result."""

    def __init__(
        self,
        *,
        service: FaultToleranceAttemptExecutor,
        persistence_boundary: FaultToleranceAttemptPersistenceBoundary,
    ) -> None:
        self.service = service
        self.persistence_boundary = persistence_boundary

    def execute_once(self) -> ProductionFaultToleranceExecutionResult:
        attempt = self.service.run_once()
        if not isinstance(attempt, FaultToleranceAttempt):
            raise TypeError(
                "fault-tolerance service must return a FaultToleranceAttempt"
            )

        persistence = self.persistence_boundary.persist(attempt)
        return ProductionFaultToleranceExecutionResult(
            attempt=attempt,
            persistence=persistence,
        )
