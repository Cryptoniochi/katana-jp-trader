"""自動更新ヘルスとランタイムメトリクスの総合判定モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.monitoring.runtime_metrics import RuntimeMetricsSnapshot
from app.monitoring.update_health_service import UpdateHealthReport


class SystemHealthStatus(StrEnum):
    """Project KATANA全体の総合状態。"""

    HEALTHY = "healthy"
    WARNING = "warning"
    DEGRADED = "degraded"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class SystemHealthPolicy:
    """総合ヘルス判定の閾値。"""

    warning_error_rate: float = 0.05
    critical_error_rate: float = 0.20
    warning_notification_failure_rate: float = 0.10
    critical_notification_failure_rate: float = 0.50

    def __post_init__(self) -> None:
        """割合閾値の範囲と大小関係を検証する。"""

        for name, value in {
            "警告エラー率": self.warning_error_rate,
            "重大エラー率": self.critical_error_rate,
            "警告通知失敗率": (
                self.warning_notification_failure_rate
            ),
            "重大通知失敗率": (
                self.critical_notification_failure_rate
            ),
        }.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"{name}は0以上1以下である必要があります。"
                )

        if self.critical_error_rate < self.warning_error_rate:
            raise ValueError(
                "重大エラー率は警告エラー率以上で"
                "ある必要があります。"
            )

        if (
            self.critical_notification_failure_rate
            < self.warning_notification_failure_rate
        ):
            raise ValueError(
                "重大通知失敗率は警告通知失敗率以上で"
                "ある必要があります。"
            )


@dataclass(frozen=True, slots=True)
class SystemHealthReport:
    """自動更新とランタイム状態を統合した総合結果。"""

    status: SystemHealthStatus
    checked_at: datetime
    update_health: UpdateHealthReport
    runtime_metrics: RuntimeMetricsSnapshot
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        """日時・理由・状態の整合性を検証する。"""

        if self.checked_at.tzinfo is None:
            raise ValueError(
                "総合ヘルス確認日時にはタイムゾーンが必要です。"
            )

        normalized_reasons = tuple(
            reason.strip()
            for reason in self.reasons
            if reason.strip()
        )

        if (
            self.status is SystemHealthStatus.HEALTHY
            and normalized_reasons
        ):
            raise ValueError(
                "正常状態には異常理由を設定できません。"
            )

        if (
            self.status is not SystemHealthStatus.HEALTHY
            and not normalized_reasons
        ):
            raise ValueError(
                "異常状態には理由が必要です。"
            )

        object.__setattr__(
            self,
            "reasons",
            normalized_reasons,
        )

    @property
    def is_healthy(self) -> bool:
        """総合状態が正常か返す。"""

        return self.status is SystemHealthStatus.HEALTHY

    @property
    def requires_attention(self) -> bool:
        """運用者の確認が必要か返す。"""

        return not self.is_healthy
