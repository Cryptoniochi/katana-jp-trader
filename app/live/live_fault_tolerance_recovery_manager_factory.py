"""Inert factory for the live RecoveryManager.

Phase 6-D Step 6C-N may assemble RecoveryManager only from already-created
dependencies. It deliberately does not construct a broker, network client,
repository, reconciliation service, portfolio service, or audit service, and
it never calls recover().
"""

from __future__ import annotations

from dataclasses import dataclass

from app.live.recovery_manager import (
    RecoveryBrokerHealthService,
    RecoveryExecutionService,
    RecoveryManager,
    RecoveryOrderRepository,
    RecoveryPortfolioAuditService,
    RecoveryPortfolioRepository,
    RecoveryPortfolioService,
)


@dataclass(frozen=True, slots=True)
class ProductionRecoveryManagerDependencies:
    """Already-created dependencies approved for RecoveryManager assembly."""

    broker: object
    health_service: RecoveryBrokerHealthService
    order_repository: RecoveryOrderRepository
    execution_service: RecoveryExecutionService
    portfolio_service: RecoveryPortfolioService
    portfolio_audit_service: RecoveryPortfolioAuditService
    portfolio_repository: RecoveryPortfolioRepository


class ProductionRecoveryManagerFactory:
    """Assemble RecoveryManager without creating or invoking dependencies."""

    @staticmethod
    def create(
        *,
        dependencies: ProductionRecoveryManagerDependencies,
    ) -> RecoveryManager:
        return RecoveryManager(
            broker=dependencies.broker,
            health_service=dependencies.health_service,
            order_repository=dependencies.order_repository,
            execution_service=dependencies.execution_service,
            portfolio_service=dependencies.portfolio_service,
            portfolio_audit_service=dependencies.portfolio_audit_service,
            portfolio_repository=dependencies.portfolio_repository,
        )
