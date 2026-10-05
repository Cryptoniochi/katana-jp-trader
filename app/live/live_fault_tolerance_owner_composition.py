"""Composition-only boundary for a production fault-tolerance owner.

The factory only assembles already-created dependencies. It intentionally does
not instantiate a live RecoveryManager because the correct production recovery
dependency is not yet approved for periodic ownership.

It also does not start the SupervisorService or execute fault tolerance.
"""

from __future__ import annotations

from app.live.live_fault_tolerance_execution_boundary import (
    ProductionFaultToleranceExecutionBoundary,
)
from app.live.live_fault_tolerance_owner import (
    FaultToleranceOwnerSupervisor,
    ProductionFaultToleranceOwner,
    ProductionFaultToleranceOwnerBundle,
)


class ProductionFaultToleranceOwnerFactory:
    """Assemble the owner without triggering lifecycle or recovery actions."""

    @staticmethod
    def create(
        *,
        supervisor: FaultToleranceOwnerSupervisor,
        execution_boundary: ProductionFaultToleranceExecutionBoundary,
    ) -> ProductionFaultToleranceOwner:
        bundle = ProductionFaultToleranceOwnerBundle(
            supervisor=supervisor,
            execution_boundary=execution_boundary,
        )
        return ProductionFaultToleranceOwner(bundle=bundle)
