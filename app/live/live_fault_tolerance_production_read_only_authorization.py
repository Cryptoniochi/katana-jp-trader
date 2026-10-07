"""Production read-only authorization adapter for fault-tolerance recovery.

Phase 6-D Step 6C-T maps the existing production read-only providers to the
6C-R recovery authorization contract. Construction is inert. Reconciliation
must exist and report literal consistent=True; missing, malformed, or provider
errors fail closed through the authorization layer.
"""

from __future__ import annotations

from typing import Protocol

from app.live.live_fault_tolerance_recovery_authorization import (
    ProductionFaultToleranceRecoveryAuthorizationProviders,
)


class ProductionReadOnlyProvidersLike(Protocol):
    runtime_health_ok_provider: object
    heartbeat_alive_provider: object
    broker_available_provider: object
    reconciliation_report_provider: object
    manual_blocked_provider: object


class ProductionFaultToleranceReadOnlyAuthorizationFactory:
    """Adapt already-created production read-only providers without evaluation."""

    @staticmethod
    def create(
        *,
        read_only_providers: ProductionReadOnlyProvidersLike,
    ) -> ProductionFaultToleranceRecoveryAuthorizationProviders:
        def manual_kill_switch_released() -> bool:
            return read_only_providers.manual_blocked_provider() is False

        def reconciliation_consistent() -> bool:
            report = read_only_providers.reconciliation_report_provider()
            if report is None:
                return False
            return getattr(report, "consistent", None) is True

        return ProductionFaultToleranceRecoveryAuthorizationProviders(
            manual_kill_switch_released=manual_kill_switch_released,
            runtime_healthy=read_only_providers.runtime_health_ok_provider,
            heartbeat_alive=read_only_providers.heartbeat_alive_provider,
            broker_available=read_only_providers.broker_available_provider,
            reconciliation_consistent=reconciliation_consistent,
        )
