"""Inert composition boundary for the production fault-tolerance runtime."""

from __future__ import annotations

from app.live.live_fault_tolerance_owner_lifecycle import ProductionFaultToleranceOwnerLifecycle
from app.live.live_fault_tolerance_runtime import (
    ProductionFaultToleranceRuntime,
    ProductionFaultToleranceRuntimeBundle,
)


class ProductionFaultToleranceRuntimeFactory:
    """Establish runtime ownership without starting the lifecycle."""

    @staticmethod
    def create(
        *,
        lifecycle: ProductionFaultToleranceOwnerLifecycle,
    ) -> ProductionFaultToleranceRuntime:
        return ProductionFaultToleranceRuntime(
            bundle=ProductionFaultToleranceRuntimeBundle(lifecycle=lifecycle)
        )
