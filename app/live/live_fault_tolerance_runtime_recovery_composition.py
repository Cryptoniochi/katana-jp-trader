"""Inert end-to-end composition for production fault-tolerance recovery.

Phase 6-D Step 6C-P joins the already-reviewed recovery, execution, owner,
lifecycle, and runtime construction boundaries. Construction remains inert.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.live.live_fault_tolerance_execution_boundary import ProductionFaultToleranceExecutionBoundary
from app.live.live_fault_tolerance_owner import FaultToleranceOwnerSupervisor, ProductionFaultToleranceOwner
from app.live.live_fault_tolerance_owner_composition import ProductionFaultToleranceOwnerFactory
from app.live.live_fault_tolerance_owner_lifecycle import ProductionFaultToleranceOwnerLifecycle
from app.live.live_fault_tolerance_persistence_boundary import FaultToleranceAttemptPersistenceBoundary
from app.live.live_fault_tolerance_recovery_composition import ProductionFaultToleranceRecoveryComposition
from app.live.live_fault_tolerance_recovery_manager_factory import ProductionRecoveryManagerDependencies
from app.live.live_fault_tolerance_runtime import ProductionFaultToleranceRuntime
from app.live.live_fault_tolerance_runtime_composition import ProductionFaultToleranceRuntimeFactory
from app.supervisor.fault_tolerance_models import FaultTolerancePolicy


@dataclass(frozen=True, slots=True)
class ProductionFaultToleranceRuntimeRecoveryBundle:
    runtime: ProductionFaultToleranceRuntime
    lifecycle: ProductionFaultToleranceOwnerLifecycle
    owner: ProductionFaultToleranceOwner
    execution_boundary: ProductionFaultToleranceExecutionBoundary


class ProductionFaultToleranceRuntimeRecoveryFactory:
    @staticmethod
    def create(
        *,
        supervisor: FaultToleranceOwnerSupervisor,
        recovery_dependencies: ProductionRecoveryManagerDependencies,
        persistence_boundary: FaultToleranceAttemptPersistenceBoundary,
        policy: FaultTolerancePolicy | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> ProductionFaultToleranceRuntimeRecoveryBundle:
        service = ProductionFaultToleranceRecoveryComposition.create(
            supervisor=supervisor,
            recovery_dependencies=recovery_dependencies,
            policy=policy,
            now_provider=now_provider,
        )
        execution_boundary = ProductionFaultToleranceExecutionBoundary(
            service=service,
            persistence_boundary=persistence_boundary,
        )
        owner = ProductionFaultToleranceOwnerFactory.create(
            supervisor=supervisor,
            execution_boundary=execution_boundary,
        )
        lifecycle = ProductionFaultToleranceOwnerLifecycle(owner=owner)
        runtime = ProductionFaultToleranceRuntimeFactory.create(lifecycle=lifecycle)
        return ProductionFaultToleranceRuntimeRecoveryBundle(
            runtime=runtime,
            lifecycle=lifecycle,
            owner=owner,
            execution_boundary=execution_boundary,
        )
