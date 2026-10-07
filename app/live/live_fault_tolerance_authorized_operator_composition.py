"""Composition for the authorized production fault-tolerance operator."""

from __future__ import annotations

from dataclasses import dataclass

from app.live.live_fault_tolerance_authorized_operator import (
    ProductionFaultToleranceAuthorizedOperatorBoundary,
)
from app.live.live_fault_tolerance_recovery_authorization import (
    ProductionFaultToleranceRecoveryAuthorization,
    ProductionFaultToleranceRecoveryAuthorizationProviders,
)
from app.live.live_fault_tolerance_recovery_authorization_composition import (
    ProductionFaultToleranceRecoveryAuthorizationFactory,
)
from app.live.live_fault_tolerance_runtime import ProductionFaultToleranceRuntime


@dataclass(frozen=True, slots=True)
class ProductionFaultToleranceAuthorizedOperatorBundle:
    operator: ProductionFaultToleranceAuthorizedOperatorBoundary
    authorization: ProductionFaultToleranceRecoveryAuthorization


class ProductionFaultToleranceAuthorizedOperatorFactory:
    """Compose the operator without starting or evaluating anything."""

    @staticmethod
    def create(
        *,
        runtime: ProductionFaultToleranceRuntime,
        providers: ProductionFaultToleranceRecoveryAuthorizationProviders,
    ) -> ProductionFaultToleranceAuthorizedOperatorBundle:
        authorization_bundle = (
            ProductionFaultToleranceRecoveryAuthorizationFactory.create(
                runtime=runtime,
                providers=providers,
            )
        )
        operator = ProductionFaultToleranceAuthorizedOperatorBoundary(
            runtime=runtime,
            gate=authorization_bundle.gate,
        )
        return ProductionFaultToleranceAuthorizedOperatorBundle(
            operator=operator,
            authorization=authorization_bundle.authorization,
        )
