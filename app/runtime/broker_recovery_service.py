"""Integrate broker health checks with recovery and event recording."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from app.broker.broker_health_models import (
    BrokerHealthCheckResult,
)
from app.runtime.broker_recovery_event_mapper import (
    map_broker_recovery_result,
)
from app.runtime.broker_recovery_models import (
    BrokerRecoveryResult,
)
from app.runtime.recovery_event_models import (
    RecoveryEvent,
)
from app.runtime.recovery_models import (
    RecoveryResult,
)
from app.runtime.recovery_service import (
    RecoveryService,
)


class BrokerRecoveryHealthService(Protocol):
    """Broker health check service."""

    def check(
        self,
        broker,
    ) -> BrokerHealthCheckResult:
        """Return the current broker health."""


class BrokerRecoveryEventRecorder(Protocol):
    """Recorder for generated recovery events."""

    def record(
        self,
        event: RecoveryEvent,
    ) -> RecoveryEvent:
        """Store and return a recovery event."""


ReconnectAction = Callable[[], bool | None]
AbortPredicate = Callable[[], bool]


class BrokerRecoveryService:
    """Recover an unhealthy broker and run a final health check."""

    def __init__(
        self,
        *,
        health_service: BrokerRecoveryHealthService,
        recovery_service: RecoveryService,
        event_recorder: (
            BrokerRecoveryEventRecorder | None
        ) = None,
    ) -> None:
        """Configure health, recovery, and optional event services."""

        self.health_service = health_service
        self.recovery_service = recovery_service
        self.event_recorder = event_recorder

    def recover_if_needed(
        self,
        *,
        broker,
        reconnect_action: ReconnectAction,
        should_abort: AbortPredicate | None = None,
    ) -> BrokerRecoveryResult:
        """Recover the broker only when its health check fails."""

        initial_health = self.health_service.check(
            broker
        )

        if initial_health.is_healthy:
            return BrokerRecoveryResult(
                initial_health=initial_health,
                recovery_result=None,
                final_health=initial_health,
            )

        recovery_result: RecoveryResult = (
            self.recovery_service.execute(
                recovery_name=(
                    f"{initial_health.broker_name} reconnect"
                ),
                action=reconnect_action,
                should_abort=should_abort,
            )
        )

        self._record_recovery_event(
            recovery_result
        )

        final_health = self.health_service.check(
            broker
        )

        return BrokerRecoveryResult(
            initial_health=initial_health,
            recovery_result=recovery_result,
            final_health=final_health,
        )

    def _record_recovery_event(
        self,
        recovery_result: RecoveryResult,
    ) -> None:
        """Record a broker event when a recorder is configured."""

        if self.event_recorder is None:
            return

        event = map_broker_recovery_result(
            recovery_result
        )
        self.event_recorder.record(event)
