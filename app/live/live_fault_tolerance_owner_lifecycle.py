"""Explicit lifecycle boundary for the production fault-tolerance owner.

Phase 6-D Step 6C-I introduces only explicit lifecycle operations:
start, heartbeat, run_once, and stop. No scheduler, thread, timer, background
loop, Paper Trading integration, or live transport activation is introduced.

The lifecycle boundary guards ordering before delegating to the existing
SupervisorService-compatible surface and the Step 6C-H owner.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.live.live_fault_tolerance_execution_boundary import (
    ProductionFaultToleranceExecutionResult,
)
from app.live.live_fault_tolerance_owner import ProductionFaultToleranceOwner
from app.supervisor.supervisor_models import (
    SupervisorSnapshot,
    SupervisorStopReason,
)


class FaultToleranceOwnerLifecycleState(StrEnum):
    """Local lifecycle state controlled by this explicit boundary."""

    STOPPED = "stopped"
    RUNNING = "running"


@dataclass(frozen=True, slots=True)
class FaultToleranceOwnerLifecycleSnapshot:
    """Result of one explicit lifecycle operation."""

    state: FaultToleranceOwnerLifecycleState
    supervisor: SupervisorSnapshot


class ProductionFaultToleranceOwnerLifecycle:
    """Order-safe explicit lifecycle for a composed production owner."""

    def __init__(self, *, owner: ProductionFaultToleranceOwner) -> None:
        self.owner = owner
        self._state = FaultToleranceOwnerLifecycleState.STOPPED

    @property
    def state(self) -> FaultToleranceOwnerLifecycleState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state is FaultToleranceOwnerLifecycleState.RUNNING

    def start(self) -> FaultToleranceOwnerLifecycleSnapshot:
        if self.is_running:
            raise RuntimeError("fault-tolerance owner lifecycle is already running")

        supervisor = self.owner.supervisor.start()
        self._state = FaultToleranceOwnerLifecycleState.RUNNING
        return FaultToleranceOwnerLifecycleSnapshot(
            state=self._state,
            supervisor=supervisor,
        )

    def heartbeat(
        self,
        *,
        occurred_at=None,
    ) -> FaultToleranceOwnerLifecycleSnapshot:
        self._require_running("heartbeat")
        supervisor = self.owner.supervisor.record_heartbeat(
            occurred_at=occurred_at
        )
        return FaultToleranceOwnerLifecycleSnapshot(
            state=self._state,
            supervisor=supervisor,
        )

    def run_once(self) -> ProductionFaultToleranceExecutionResult:
        self._require_running("run_once")
        return self.owner.run_once()

    def stop(
        self,
        *,
        reason: SupervisorStopReason = SupervisorStopReason.MANUAL,
        message: str | None = None,
    ) -> FaultToleranceOwnerLifecycleSnapshot:
        self._require_running("stop")
        supervisor = self.owner.supervisor.stop(
            reason=reason,
            message=message,
        )
        self._state = FaultToleranceOwnerLifecycleState.STOPPED
        return FaultToleranceOwnerLifecycleSnapshot(
            state=self._state,
            supervisor=supervisor,
        )

    def _require_running(self, operation: str) -> None:
        if not self.is_running:
            raise RuntimeError(
                f"fault-tolerance owner lifecycle must be running before {operation}"
            )
