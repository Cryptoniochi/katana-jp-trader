"""Inert service composition for production fault tolerance.

Phase 6-D Step 6C-L intentionally requires an already-created recovery
dependency. The factory may compose FaultToleranceService around that dependency,
but it must not construct RecoveryManager or any broker-facing dependency.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.live.live_fault_tolerance_production_dependencies import (
    ProductionFaultToleranceDependencies,
)
from app.supervisor.fault_tolerance_models import FaultTolerancePolicy
from app.supervisor.fault_tolerance_service import (
    FaultToleranceService,
    FaultToleranceSupervisor,
)


class ProductionFaultToleranceServiceFactory:
    """Compose FaultToleranceService without choosing a recovery implementation."""

    @staticmethod
    def create(
        *,
        supervisor: FaultToleranceSupervisor,
        dependencies: ProductionFaultToleranceDependencies,
        policy: FaultTolerancePolicy | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> FaultToleranceService:
        return FaultToleranceService(
            supervisor=supervisor,
            recovery_manager=dependencies.recovery,
            policy=policy,
            now_provider=now_provider,
        )
