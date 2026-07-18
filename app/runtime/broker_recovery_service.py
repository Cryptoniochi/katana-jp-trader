"""Broker診断とRecoveryServiceを統合する。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from app.broker.broker_health_models import (
    BrokerHealthCheckResult,
)
from app.runtime.broker_recovery_models import (
    BrokerRecoveryResult,
)
from app.runtime.recovery_models import (
    RecoveryResult,
)
from app.runtime.recovery_service import (
    RecoveryService,
)


class BrokerRecoveryHealthService(Protocol):
    """Broker診断処理。"""

    def check(
        self,
        broker,
    ) -> BrokerHealthCheckResult:
        """Broker Healthを返す。"""


ReconnectAction = Callable[[], bool | None]
AbortPredicate = Callable[[], bool]


class BrokerRecoveryService:
    """Broker異常時に再接続処理を試行して再診断する。"""

    def __init__(
        self,
        *,
        health_service: BrokerRecoveryHealthService,
        recovery_service: RecoveryService,
    ) -> None:
        """診断・復旧Serviceを設定する。"""

        self.health_service = health_service
        self.recovery_service = recovery_service

    def recover_if_needed(
        self,
        *,
        broker,
        reconnect_action: ReconnectAction,
        should_abort: AbortPredicate | None = None,
    ) -> BrokerRecoveryResult:
        """Brokerを診断し、必要な場合だけ復旧する。"""

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

        final_health = self.health_service.check(
            broker
        )

        return BrokerRecoveryResult(
            initial_health=initial_health,
            recovery_result=recovery_result,
            final_health=final_health,
        )
