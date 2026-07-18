"""Runtime HealthとRecoveryServiceを統合する。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from app.runtime.recovery_event_models import (
    RecoveryEventCategory,
)
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


class RuntimeRecoveryEventRecorder(Protocol):
    """Runtime復旧結果をEventとして記録する。"""

    def record_runtime_result(
        self,
        result: RecoveryResult,
        *,
        category: RecoveryEventCategory,
    ) -> object:
        """Runtime復旧結果を記録する。"""


RestartAction = Callable[[], bool | None]
AbortPredicate = Callable[[], bool]


class RuntimeRecoveryService:
    """Runtime異常時に再起動処理を試行して再診断する。"""

    def __init__(
        self,
        *,
        health_reader: RuntimeRecoveryHealthReader,
        recovery_service: RecoveryService,
        event_recorder: (
            RuntimeRecoveryEventRecorder | None
        ) = None,
        recover_warning: bool = False,
    ) -> None:
        """Health Reader・Recovery Service・記録先を設定する。"""

        self.health_reader = health_reader
        self.recovery_service = recovery_service
        self.event_recorder = event_recorder
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

        self._record_recovery_event(recovery_result)

        final_health = self.health_reader.check()

        return RuntimeRecoveryResult(
            runtime_name=name,
            initial_health=initial_health,
            recovery_result=recovery_result,
            final_health=final_health,
        )

    def _record_recovery_event(
        self,
        recovery_result: RecoveryResult,
    ) -> None:
        """設定されている場合だけ復旧結果を記録する。"""

        if self.event_recorder is None:
            return

        self.event_recorder.record_runtime_result(
            recovery_result,
            category=RecoveryEventCategory.RESTART,
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