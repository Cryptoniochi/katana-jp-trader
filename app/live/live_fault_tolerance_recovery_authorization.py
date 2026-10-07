"""Fail-closed authorization policy for production fault-tolerance recovery.

Phase 6-D Step 6C-R defines the concrete safety inputs that may authorize the
Step 6C-Q execution gate. This module only evaluates injected read-only
providers. It does not start a runtime, execute recovery, persist state,
access a broker, or change any live-order hard lock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class BooleanSafetyProvider(Protocol):
    def __call__(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class ProductionFaultToleranceRecoveryAuthorizationProviders:
    manual_kill_switch_released: BooleanSafetyProvider
    runtime_healthy: BooleanSafetyProvider
    heartbeat_alive: BooleanSafetyProvider
    broker_available: BooleanSafetyProvider
    reconciliation_consistent: BooleanSafetyProvider


@dataclass(frozen=True, slots=True)
class ProductionFaultToleranceRecoveryAuthorizationSnapshot:
    manual_kill_switch_released: bool
    runtime_healthy: bool
    heartbeat_alive: bool
    broker_available: bool
    reconciliation_consistent: bool
    authorized: bool
    reason: str


class ProductionFaultToleranceRecoveryAuthorization:
    """Require every reviewed safety input to be literal True."""

    def __init__(
        self,
        *,
        providers: ProductionFaultToleranceRecoveryAuthorizationProviders,
    ) -> None:
        self.providers = providers
        self._last_snapshot: ProductionFaultToleranceRecoveryAuthorizationSnapshot | None = None

    @property
    def last_snapshot(self) -> ProductionFaultToleranceRecoveryAuthorizationSnapshot | None:
        return self._last_snapshot

    def __call__(self) -> bool:
        snapshot = self.evaluate()
        return snapshot.authorized

    def evaluate(self) -> ProductionFaultToleranceRecoveryAuthorizationSnapshot:
        names = (
            "manual_kill_switch_released",
            "runtime_healthy",
            "heartbeat_alive",
            "broker_available",
            "reconciliation_consistent",
        )
        values: dict[str, bool] = {}

        for name in names:
            provider = getattr(self.providers, name)
            try:
                value = provider()
            except Exception as error:
                snapshot = self._blocked_snapshot(
                    values=values,
                    failed=name,
                    reason=(
                        f"{name} provider failed closed: "
                        f"{type(error).__name__}: {error}"
                    ),
                )
                self._last_snapshot = snapshot
                return snapshot

            if value is not True:
                snapshot = self._blocked_snapshot(
                    values=values,
                    failed=name,
                    reason=f"{name} was not explicitly safe",
                )
                self._last_snapshot = snapshot
                return snapshot

            values[name] = True

        snapshot = ProductionFaultToleranceRecoveryAuthorizationSnapshot(
            manual_kill_switch_released=True,
            runtime_healthy=True,
            heartbeat_alive=True,
            broker_available=True,
            reconciliation_consistent=True,
            authorized=True,
            reason="all production fault-tolerance recovery safety inputs are safe",
        )
        self._last_snapshot = snapshot
        return snapshot

    @staticmethod
    def _blocked_snapshot(
        *,
        values: dict[str, bool],
        failed: str,
        reason: str,
    ) -> ProductionFaultToleranceRecoveryAuthorizationSnapshot:
        defaults = {
            "manual_kill_switch_released": False,
            "runtime_healthy": False,
            "heartbeat_alive": False,
            "broker_available": False,
            "reconciliation_consistent": False,
        }
        defaults.update(values)
        defaults[failed] = False
        return ProductionFaultToleranceRecoveryAuthorizationSnapshot(
            **defaults,
            authorized=False,
            reason=reason,
        )
