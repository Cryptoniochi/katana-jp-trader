"""Phase 6-E Step 2: production read-only Live activation composition.

Adapts the existing production read-only provider bundle to the Phase 6-E
activation authorization contract. Construction is inert: providers are not
evaluated and no unlock, runtime execution, broker transport, or order
submission capability is created.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from app.live.live_activation_authorization import (
    LiveActivationAuthorizationGate,
    LiveActivationAuthorizationProviders,
    NowProvider,
)


BoolProvider = Callable[[], bool]


class ProductionLiveActivationReadOnlyProvidersLike(Protocol):
    runtime_health_ok_provider: object
    heartbeat_alive_provider: object
    broker_available_provider: object
    reconciliation_report_provider: object
    manual_blocked_provider: object


class ProductionLiveActivationAuthorizationFactory:
    """Compose the activation gate from already-created read-only providers."""

    @staticmethod
    def create(
        *,
        read_only_providers: ProductionLiveActivationReadOnlyProvidersLike,
        final_readiness_activation_ready_provider: BoolProvider,
        now_provider: NowProvider | None = None,
    ) -> LiveActivationAuthorizationGate:
        def manual_kill_switch_released() -> bool:
            return read_only_providers.manual_blocked_provider() is False

        def reconciliation_consistent() -> bool:
            report = read_only_providers.reconciliation_report_provider()
            if report is None:
                return False
            return getattr(report, "consistent", None) is True

        providers = LiveActivationAuthorizationProviders(
            final_readiness_activation_ready=(
                final_readiness_activation_ready_provider
            ),
            manual_kill_switch_released=manual_kill_switch_released,
            runtime_healthy=read_only_providers.runtime_health_ok_provider,
            heartbeat_alive=read_only_providers.heartbeat_alive_provider,
            broker_available=read_only_providers.broker_available_provider,
            reconciliation_consistent=reconciliation_consistent,
        )
        return LiveActivationAuthorizationGate(
            providers=providers,
            now_provider=now_provider,
        )
