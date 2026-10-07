"""Phase 6-E Step 1: inert Live activation authorization contract.

This layer answers only whether all reviewed prerequisites for a future Live
unlock are satisfied. It cannot unlock anything and deliberately requires
all three hard locks to remain closed while authorization is evaluated.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

BoolProvider = Callable[[], bool]
NowProvider = Callable[[], datetime]


class LiveActivationAuthorizationState(StrEnum):
    BLOCKED = "blocked"
    AUTHORIZATION_READY = "authorization_ready"


@dataclass(frozen=True, slots=True)
class LiveActivationAuthorizationItem:
    key: str
    passed: bool
    message: str


@dataclass(frozen=True, slots=True)
class LiveActivationAuthorizationReport:
    generated_at: datetime
    authorization_ready: bool
    state: LiveActivationAuthorizationState
    items: tuple[LiveActivationAuthorizationItem, ...]

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware.")


@dataclass(frozen=True, slots=True)
class LiveActivationAuthorizationProviders:
    final_readiness_activation_ready: BoolProvider
    manual_kill_switch_released: BoolProvider
    runtime_healthy: BoolProvider
    heartbeat_alive: BoolProvider
    broker_available: BoolProvider
    reconciliation_consistent: BoolProvider


class LiveActivationAuthorizationGate:
    """Fail-closed authorization gate with no unlock capability."""

    def __init__(self, *, providers, now_provider=None) -> None:
        self.providers = providers
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def check(self) -> LiveActivationAuthorizationReport:
        items = (
            self._check("final_live_readiness", self.providers.final_readiness_activation_ready),
            self._check("manual_kill_switch", self.providers.manual_kill_switch_released),
            self._check("runtime_health", self.providers.runtime_healthy),
            self._check("heartbeat", self.providers.heartbeat_alive),
            self._check("broker_availability", self.providers.broker_available),
            self._check("reconciliation", self.providers.reconciliation_consistent),
            self._hard_lock_item("live_order_transmission_hard_lock", self._live_order_transmission_locked),
            self._hard_lock_item("live_broker_transport_hard_lock", self._live_broker_transport_locked),
            self._hard_lock_item("locked_live_runtime_integration_hard_lock", self._live_runtime_integration_locked),
        )
        ready = all(item.passed for item in items)
        return LiveActivationAuthorizationReport(
            generated_at=self._now(),
            authorization_ready=ready,
            state=(LiveActivationAuthorizationState.AUTHORIZATION_READY
                   if ready else LiveActivationAuthorizationState.BLOCKED),
            items=items,
        )

    @staticmethod
    def _check(key, provider):
        try:
            passed = provider() is True
        except Exception as error:
            return LiveActivationAuthorizationItem(
                key, False,
                f"Unavailable or invalid: {type(error).__name__}: {error}",
            )
        return LiveActivationAuthorizationItem(
            key, passed, "ready" if passed else "blocked"
        )

    @staticmethod
    def _hard_lock_item(key, provider):
        try:
            locked = provider() is True
        except Exception as error:
            return LiveActivationAuthorizationItem(
                key, False,
                f"Hard-lock state unavailable: {type(error).__name__}: {error}",
            )
        return LiveActivationAuthorizationItem(
            key, locked,
            "hard lock remains closed" if locked else "hard lock is not closed",
        )

    @staticmethod
    def _live_order_transmission_locked() -> bool:
        from app.live.live_order_adapter import LIVE_ORDER_TRANSMISSION_ENABLED
        return LIVE_ORDER_TRANSMISSION_ENABLED is False

    @staticmethod
    def _live_broker_transport_locked() -> bool:
        from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
        return LIVE_BROKER_TRANSPORT_ENABLED is False

    @staticmethod
    def _live_runtime_integration_locked() -> bool:
        from app.live.locked_live_runtime_integration import (
            LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
        )
        return LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False

    def _now(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)
