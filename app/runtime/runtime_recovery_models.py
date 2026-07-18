"""Runtime自動復旧の共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass

from app.runtime.recovery_models import RecoveryResult
from app.runtime.runtime_health_monitor_models import (
    RuntimeHealthMonitorReport,
    RuntimeHealthStatus,
)


@dataclass(frozen=True, slots=True)
class RuntimeRecoveryResult:
    """Runtime診断・復旧・再診断の結果。"""

    runtime_name: str
    initial_health: RuntimeHealthMonitorReport
    recovery_result: RecoveryResult | None
    final_health: RuntimeHealthMonitorReport

    def __post_init__(self) -> None:
        """Runtime名と復旧有無の整合性を検証する。"""

        runtime_name = self.runtime_name.strip()

        if not runtime_name:
            raise ValueError(
                "Runtime名を指定してください。"
            )

        if (
            self.initial_health.status
            is RuntimeHealthStatus.HEALTHY
            and self.recovery_result is not None
        ):
            raise ValueError(
                "正常Runtimeに復旧結果は設定できません。"
            )

        object.__setattr__(
            self,
            "runtime_name",
            runtime_name,
        )

    @property
    def recovery_attempted(self) -> bool:
        """復旧処理を実行したか返す。"""

        return self.recovery_result is not None

    @property
    def recovered(self) -> bool:
        """復旧後にRuntimeが正常化したか返す。"""

        return (
            self.final_health.status
            in {
                RuntimeHealthStatus.HEALTHY,
                RuntimeHealthStatus.IDLE,
            }
            and (
                self.recovery_result is None
                or self.recovery_result.succeeded
            )
        )

    @property
    def requires_attention(self) -> bool:
        """最終状態に運用者の確認が必要か返す。"""

        return self.final_health.requires_attention
