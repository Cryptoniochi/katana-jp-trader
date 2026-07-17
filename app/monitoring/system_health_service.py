"""既存の更新ヘルスとランタイムメトリクスを統合評価する。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from app.monitoring.runtime_metrics import RuntimeMetricsSnapshot
from app.monitoring.system_health_models import (
    SystemHealthPolicy,
    SystemHealthReport,
    SystemHealthStatus,
)
from app.monitoring.update_health_service import (
    UpdateHealthReport,
    UpdateHealthStatus,
)


class UpdateHealthChecker(Protocol):
    """既存の自動更新ヘルスチェック。"""

    def check(self) -> UpdateHealthReport:
        """現在の自動更新ヘルスを返す。"""


class RuntimeMetricsReader(Protocol):
    """ランタイムメトリクスの読み取り処理。"""

    def snapshot(self) -> RuntimeMetricsSnapshot:
        """現在のランタイムメトリクスを返す。"""


class SystemHealthService:
    """更新基盤とランタイム運用状態を総合評価する。"""

    def __init__(
        self,
        *,
        update_health_service: UpdateHealthChecker,
        runtime_metrics_service: RuntimeMetricsReader,
        policy: SystemHealthPolicy | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """依存関係・閾値・時計を設定する。"""

        self.update_health_service = update_health_service
        self.runtime_metrics_service = runtime_metrics_service
        self.policy = policy or SystemHealthPolicy()
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def check(self) -> SystemHealthReport:
        """現在の総合ヘルスを返す。"""

        checked_at = self._current_time()
        update_health = self.update_health_service.check()
        runtime_metrics = self.runtime_metrics_service.snapshot()

        reasons: list[str] = []
        severity = 0

        update_severity = {
            UpdateHealthStatus.HEALTHY: 0,
            UpdateHealthStatus.WARNING: 1,
            UpdateHealthStatus.ERROR: 3,
        }[update_health.status]

        if update_severity > 0:
            severity = max(severity, update_severity)
            reasons.append(
                "自動更新基盤: "
                f"{update_health.status.value} - "
                f"{update_health.reason}"
            )

        runtime_error_rate = runtime_metrics.error_rate

        if (
            runtime_error_rate
            >= self.policy.critical_error_rate
        ):
            severity = max(severity, 3)
            reasons.append(
                "ランタイムエラー率が重大閾値以上です。 "
                f"error_rate={runtime_error_rate:.4f}"
            )
        elif (
            runtime_error_rate
            >= self.policy.warning_error_rate
        ):
            severity = max(severity, 1)
            reasons.append(
                "ランタイムエラー率が警告閾値以上です。 "
                f"error_rate={runtime_error_rate:.4f}"
            )

        notification_failure_rate = (
            runtime_metrics.notification_failure_rate
        )

        if (
            notification_failure_rate
            >= self.policy
            .critical_notification_failure_rate
        ):
            severity = max(severity, 2)
            reasons.append(
                "通知失敗率が重大閾値以上です。 "
                "notification_failure_rate="
                f"{notification_failure_rate:.4f}"
            )
        elif (
            notification_failure_rate
            >= self.policy
            .warning_notification_failure_rate
        ):
            severity = max(severity, 1)
            reasons.append(
                "通知失敗率が警告閾値以上です。 "
                "notification_failure_rate="
                f"{notification_failure_rate:.4f}"
            )

        status = {
            0: SystemHealthStatus.HEALTHY,
            1: SystemHealthStatus.WARNING,
            2: SystemHealthStatus.DEGRADED,
            3: SystemHealthStatus.CRITICAL,
        }[severity]

        return SystemHealthReport(
            status=status,
            checked_at=checked_at,
            update_health=update_health,
            runtime_metrics=runtime_metrics,
            reasons=tuple(reasons),
        )

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
