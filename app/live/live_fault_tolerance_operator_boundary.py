"""Operator-facing one-shot boundary for production fault tolerance.

Phase 6-D Step 6C-K owns one explicit operator invocation:
start -> heartbeat -> run_once -> stop.

The boundary is fail-safe with respect to lifecycle cleanup: once start succeeds,
stop is attempted from finally even when heartbeat or run_once raises. It does
not schedule repeated work and does not construct recovery or live transport.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.live.live_fault_tolerance_execution_boundary import (
    ProductionFaultToleranceExecutionResult,
)
from app.live.live_fault_tolerance_owner_lifecycle import (
    FaultToleranceOwnerLifecycleSnapshot,
)
from app.live.live_fault_tolerance_runtime import ProductionFaultToleranceRuntime
from app.supervisor.supervisor_models import SupervisorStopReason


@dataclass(frozen=True, slots=True)
class ProductionFaultToleranceOperatorResult:
    """Completed one-shot operator invocation."""

    start: FaultToleranceOwnerLifecycleSnapshot
    heartbeat: FaultToleranceOwnerLifecycleSnapshot
    execution: ProductionFaultToleranceExecutionResult
    stop: FaultToleranceOwnerLifecycleSnapshot


class ProductionFaultToleranceOperatorBoundary:
    """Run one explicit fault-tolerance cycle and always close its lifecycle."""

    def __init__(self, *, runtime: ProductionFaultToleranceRuntime) -> None:
        self.runtime = runtime

    def run_once(self) -> ProductionFaultToleranceOperatorResult:
        start_result = self.runtime.start()
        heartbeat_result = None
        execution_result = None
        stop_result = None

        try:
            heartbeat_result = self.runtime.heartbeat()
            execution_result = self.runtime.run_once()
        finally:
            stop_result = self.runtime.stop(
                reason=SupervisorStopReason.NORMAL,
                message="operator one-shot completed",
            )

        if heartbeat_result is None or execution_result is None or stop_result is None:
            raise RuntimeError("operator one-shot did not complete")

        return ProductionFaultToleranceOperatorResult(
            start=start_result,
            heartbeat=heartbeat_result,
            execution=execution_result,
            stop=stop_result,
        )
