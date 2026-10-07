"""Authorized one-shot operator for production fault-tolerance recovery.

Phase 6-D Step 6C-S composes the explicit runtime lifecycle with the 6C-Q
fail-closed gate and 6C-R authorization. One call performs:
start -> heartbeat -> authorization/gate -> stop.

A blocked gate is a successful safe outcome: recovery is not executed, and
the runtime is still stopped in finally. No scheduler or background ownership
is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.live.live_fault_tolerance_execution_gate import (
    ProductionFaultToleranceExecutionGate,
    ProductionFaultToleranceExecutionGateResult,
)
from app.live.live_fault_tolerance_owner_lifecycle import (
    FaultToleranceOwnerLifecycleSnapshot,
)
from app.live.live_fault_tolerance_runtime import ProductionFaultToleranceRuntime
from app.supervisor.supervisor_models import SupervisorStopReason


@dataclass(frozen=True, slots=True)
class ProductionFaultToleranceAuthorizedOperatorResult:
    start: FaultToleranceOwnerLifecycleSnapshot
    heartbeat: FaultToleranceOwnerLifecycleSnapshot
    gate: ProductionFaultToleranceExecutionGateResult
    stop: FaultToleranceOwnerLifecycleSnapshot


class ProductionFaultToleranceAuthorizedOperatorBoundary:
    """Run exactly one explicitly authorized production lifecycle."""

    def __init__(
        self,
        *,
        runtime: ProductionFaultToleranceRuntime,
        gate: ProductionFaultToleranceExecutionGate,
    ) -> None:
        self.runtime = runtime
        self.gate = gate
        if self.gate.runtime is not self.runtime:
            raise ValueError("gate and operator must own the same runtime")

    def run_once(self) -> ProductionFaultToleranceAuthorizedOperatorResult:
        start_result = self.runtime.start()
        heartbeat_result = None
        gate_result = None
        stop_result = None

        try:
            heartbeat_result = self.runtime.heartbeat()
            gate_result = self.gate.run_once()
        finally:
            stop_result = self.runtime.stop(
                reason=SupervisorStopReason.NORMAL,
                message="authorized operator one-shot completed",
            )

        if heartbeat_result is None or gate_result is None or stop_result is None:
            raise RuntimeError("authorized operator one-shot did not complete")

        return ProductionFaultToleranceAuthorizedOperatorResult(
            start=start_result,
            heartbeat=heartbeat_result,
            gate=gate_result,
            stop=stop_result,
        )
