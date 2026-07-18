"""Broker自動復旧の共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass

from app.broker.broker_health_models import (
    BrokerHealthCheckResult,
)
from app.runtime.recovery_models import (
    RecoveryResult,
)


@dataclass(frozen=True, slots=True)
class BrokerRecoveryResult:
    """Broker診断・復旧・再診断の結果。"""

    initial_health: BrokerHealthCheckResult
    recovery_result: RecoveryResult | None
    final_health: BrokerHealthCheckResult

    def __post_init__(self) -> None:
        """Broker名と復旧有無の整合性を検証する。"""

        broker_names = {
            self.initial_health.broker_name,
            self.final_health.broker_name,
        }

        if len(broker_names) != 1:
            raise ValueError(
                "復旧前後のBroker名が一致しません。"
            )

        if (
            self.initial_health.is_healthy
            and self.recovery_result is not None
        ):
            raise ValueError(
                "正常Brokerに復旧結果は設定できません。"
            )

    @property
    def broker_name(self) -> str:
        """Broker名を返す。"""

        return self.initial_health.broker_name

    @property
    def recovery_attempted(self) -> bool:
        """復旧処理を実行したか返す。"""

        return self.recovery_result is not None

    @property
    def recovered(self) -> bool:
        """復旧後にBrokerが正常化したか返す。"""

        return (
            self.final_health.is_healthy
            and (
                self.recovery_result is None
                or self.recovery_result.succeeded
            )
        )
