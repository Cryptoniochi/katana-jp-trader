"""Runtime HealthとRecoveryServiceを統合する。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from app.runtime.recovery_models import RecoveryResult
from app.runtime.recovery_service import RecoveryService
from app.runtime.runtime_health_monitor_models import (
    RuntimeHealthMonitorReport,
    RuntimeHealthStatus,
)
from app.runtime.runtime_recovery_models import (
    RuntimeRecoveryResult,
)


class RuntimeRecoveryHealthReader(Protocol):
    """Runtime Health Reader。"""

    def check(self) -> RuntimeHealthMonitorReport:
        """現在のRuntime Healthを返す。"""


RestartAction = Callable[[], bool | None]
AbortPredicate = Callable[[], bool]


class RuntimeRecoveryService:
    """Runtime異常時に再起動処理を試行して再診断する。"""

    def __init__(
        self,
        *,
        health_reader: RuntimeRecoveryHealthReader,
        recovery_service: RecoveryService,
        recover_warning: bool = False,
    ) -> None:
        """Health Reader・Recovery Service・警告時方針を設定する。"""

        self.health_reader = health_reader
        self.recovery_service = recovery_service
        self.recover_warning = recover_warning

    def recover_if_needed(
        self,
        *,
        runtime_name: str,
        restart_action: RestartAction,
        should_abort: AbortPredicate | None = None,
    ) -> RuntimeRecoveryResult:
        """Runtimeを診断し、必要な場合だけ復旧する。"""

        name = runtime_name.strip()

        if not name:
            raise ValueError(
                "Runtime名を指定してください。"
            )

        initial_health = self.health_reader.check()

        if not self._requires_recovery(
            initial_health.status
        ):
            return RuntimeRecoveryResult(
                runtime_name=name,
                initial_health=initial_health,
                recovery_result=None,
                final_health=initial_health,
            )

        recovery_result: RecoveryResult = (
            self.recovery_service.execute(
                recovery_name=f"{name} restart",
                action=restart_action,
                should_abort=should_abort,
            )
        )

        final_health = self.health_reader.check()

        return RuntimeRecoveryResult(
            runtime_name=name,
            initial_health=initial_health,
            recovery_result=recovery_result,
            final_health=final_health,
        )

    def _requires_recovery(
        self,
        status: RuntimeHealthStatus,
    ) -> bool:
        """Health状態から復旧が必要か返す。"""

        if status in {
            RuntimeHealthStatus.CRITICAL,
            RuntimeHealthStatus.STOPPED,
        }:
            return True

        if (
            status is RuntimeHealthStatus.WARNING
            and self.recover_warning
        ):
            return True

        return False
