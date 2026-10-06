"""Explicit production runtime shell for the fault-tolerance owner lifecycle.

Phase 6-D Step 6C-J establishes who owns the Step 6C-I lifecycle without
introducing scheduling. Construction is inert; lifecycle actions remain explicit.
"""

from __future__ import annotations
from dataclasses import dataclass

from app.live.live_fault_tolerance_execution_boundary import ProductionFaultToleranceExecutionResult
from app.live.live_fault_tolerance_owner_lifecycle import (
    FaultToleranceOwnerLifecycleSnapshot,
    ProductionFaultToleranceOwnerLifecycle,
)
from app.supervisor.supervisor_models import SupervisorStopReason


@dataclass(frozen=True, slots=True)
class ProductionFaultToleranceRuntimeBundle:
    lifecycle: ProductionFaultToleranceOwnerLifecycle


class ProductionFaultToleranceRuntime:
    """Top-level explicit owner of the fault-tolerance lifecycle."""

    def __init__(self, *, bundle: ProductionFaultToleranceRuntimeBundle) -> None:
        self.bundle = bundle

    @property
    def lifecycle(self) -> ProductionFaultToleranceOwnerLifecycle:
        return self.bundle.lifecycle

    @property
    def is_running(self) -> bool:
        return self.lifecycle.is_running

    def start(self) -> FaultToleranceOwnerLifecycleSnapshot:
        return self.lifecycle.start()

    def heartbeat(self, *, occurred_at=None) -> FaultToleranceOwnerLifecycleSnapshot:
        return self.lifecycle.heartbeat(occurred_at=occurred_at)

    def run_once(self) -> ProductionFaultToleranceExecutionResult:
        return self.lifecycle.run_once()

    def stop(
        self,
        *,
        reason: SupervisorStopReason = SupervisorStopReason.MANUAL,
        message: str | None = None,
    ) -> FaultToleranceOwnerLifecycleSnapshot:
        return self.lifecycle.stop(reason=reason, message=message)
