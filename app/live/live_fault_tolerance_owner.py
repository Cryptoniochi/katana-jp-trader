"""Inert production owner for the fault-tolerance execution boundary.

Phase 6-D Step 6C-H deliberately separates ownership/lifecycle from scheduling.
Construction never starts a supervisor, records a heartbeat, executes recovery,
or writes durable fault-tolerance state.

A later reviewed runtime may explicitly call run_once(). No loop, timer, thread,
or Paper Trading integration is introduced here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.live.live_fault_tolerance_execution_boundary import (
    ProductionFaultToleranceExecutionBoundary,
    ProductionFaultToleranceExecutionResult,
)


class FaultToleranceOwnerSupervisor(Protocol):
    """Supervisor lifecycle surface owned by a future production runtime."""

    def start(self): ...

    def record_heartbeat(self, *, occurred_at=None): ...

    def check(self): ...


@dataclass(frozen=True, slots=True)
class ProductionFaultToleranceOwnerBundle:
    """Dependencies owned by the production fault-tolerance lifecycle."""

    supervisor: FaultToleranceOwnerSupervisor
    execution_boundary: ProductionFaultToleranceExecutionBoundary


class ProductionFaultToleranceOwner:
    """Explicit owner with an inert constructor and one-shot execution method."""

    def __init__(self, *, bundle: ProductionFaultToleranceOwnerBundle) -> None:
        self.bundle = bundle

    @property
    def supervisor(self) -> FaultToleranceOwnerSupervisor:
        return self.bundle.supervisor

    @property
    def execution_boundary(self) -> ProductionFaultToleranceExecutionBoundary:
        return self.bundle.execution_boundary

    def run_once(self) -> ProductionFaultToleranceExecutionResult:
        """Run one already-composed fault-tolerance evaluation explicitly."""

        return self.execution_boundary.execute_once()
