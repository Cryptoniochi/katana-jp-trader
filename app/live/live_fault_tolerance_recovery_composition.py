"""Inert composition boundary joining RecoveryManager and FaultToleranceService.

Phase 6-D Step 6C-O composes the two already-reviewed factories, but remains
construction-only. It does not call FaultToleranceService.run_once(),
RecoveryManager.recover(), or any operational dependency.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.live.live_fault_tolerance_production_composition import (
    ProductionFaultToleranceServiceFactory,
)
from app.live.live_fault_tolerance_production_dependencies import (
    ProductionFaultToleranceDependencies,
)
from app.live.live_fault_tolerance_recovery_manager_factory import (
    ProductionRecoveryManagerDependencies,
    ProductionRecoveryManagerFactory,
)
from app.supervisor.fault_tolerance_models import FaultTolerancePolicy
from app.supervisor.fault_tolerance_service import (
    FaultToleranceService,
    FaultToleranceSupervisor,
)


class ProductionFaultToleranceRecoveryComposition:
    """Compose fault tolerance around an inertly assembled RecoveryManager."""

    @staticmethod
    def create(
        *,
        supervisor: FaultToleranceSupervisor,
        recovery_dependencies: ProductionRecoveryManagerDependencies,
        policy: FaultTolerancePolicy | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> FaultToleranceService:
        recovery_manager = ProductionRecoveryManagerFactory.create(
            dependencies=recovery_dependencies,
        )
        fault_tolerance_dependencies = ProductionFaultToleranceDependencies(
            recovery=recovery_manager,
        )
        return ProductionFaultToleranceServiceFactory.create(
            supervisor=supervisor,
            dependencies=fault_tolerance_dependencies,
            policy=policy,
            now_provider=now_provider,
        )
