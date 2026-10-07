"""Composition boundary joining recovery authorization to the 6C-Q gate."""

from __future__ import annotations

from dataclasses import dataclass

from app.live.live_fault_tolerance_execution_gate import (
    ProductionFaultToleranceExecutionGate,
)
from app.live.live_fault_tolerance_recovery_authorization import (
    ProductionFaultToleranceRecoveryAuthorization,
    ProductionFaultToleranceRecoveryAuthorizationProviders,
)
from app.live.live_fault_tolerance_runtime import ProductionFaultToleranceRuntime


@dataclass(frozen=True, slots=True)
class ProductionFaultToleranceRecoveryAuthorizationBundle:
    gate: ProductionFaultToleranceExecutionGate
    authorization: ProductionFaultToleranceRecoveryAuthorization


class ProductionFaultToleranceRecoveryAuthorizationFactory:
    """Compose read-only authorization with an already-created runtime."""

    @staticmethod
    def create(
        *,
        runtime: ProductionFaultToleranceRuntime,
        providers: ProductionFaultToleranceRecoveryAuthorizationProviders,
    ) -> ProductionFaultToleranceRecoveryAuthorizationBundle:
        authorization = ProductionFaultToleranceRecoveryAuthorization(
            providers=providers,
        )
        gate = ProductionFaultToleranceExecutionGate(
            runtime=runtime,
            authorization_provider=authorization,
        )
        return ProductionFaultToleranceRecoveryAuthorizationBundle(
            gate=gate,
            authorization=authorization,
        )
