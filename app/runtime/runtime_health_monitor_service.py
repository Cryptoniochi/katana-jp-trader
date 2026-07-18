"""RuntimeのHeartbeat・Cycle停滞を判定する。"""

from __future__ import annotations

from app.runtime.runtime_health_monitor_models import (
    RuntimeActivitySnapshot,
    RuntimeHealthMonitorPolicy,
    RuntimeHealthMonitorReport,
    RuntimeHealthStatus,
)


class RuntimeHealthMonitorService:
    """最新活動時刻からRuntime状態を判定する。"""

    def __init__(
        self,
        *,
        policy: RuntimeHealthMonitorPolicy | None = None,
    ) -> None:
        """判定Policyを設定する。"""

        self.policy = (
            policy
            if policy is not None
            else RuntimeHealthMonitorPolicy()
        )

    def evaluate(
        self,
        snapshot: RuntimeActivitySnapshot,
    ) -> RuntimeHealthMonitorReport:
        """Runtime Activityを判定する。"""

        if not snapshot.running:
            return RuntimeHealthMonitorReport(
                status=RuntimeHealthStatus.STOPPED,
                checked_at=snapshot.checked_at,
                running=False,
                heartbeat_age_seconds=self._age(
                    snapshot.checked_at,
                    snapshot.last_heartbeat_at,
                ),
                cycle_age_seconds=self._age(
                    snapshot.checked_at,
                    snapshot.last_cycle_at,
                ),
                reasons=(
                    "Runtimeが稼働状態ではありません。",
                ),
            )

        heartbeat_age = self._age(
            snapshot.checked_at,
            snapshot.last_heartbeat_at,
        )
        cycle_age = self._age(
            snapshot.checked_at,
            snapshot.last_cycle_at,
        )

        if (
            snapshot.last_heartbeat_at is None
            and snapshot.last_cycle_at is None
        ):
            return RuntimeHealthMonitorReport(
                status=RuntimeHealthStatus.IDLE,
                checked_at=snapshot.checked_at,
                running=True,
                heartbeat_age_seconds=None,
                cycle_age_seconds=None,
                reasons=(),
            )

        reasons: list[str] = []
        severity = 0

        if heartbeat_age is None:
            severity = max(severity, 1)
            reasons.append(
                "Heartbeatがまだ記録されていません。"
            )
        elif (
            heartbeat_age
            >= self.policy.heartbeat_critical_seconds
        ):
            severity = max(severity, 2)
            reasons.append(
                "Heartbeatが重大閾値を超えて停止しています。 "
                f"age_seconds={heartbeat_age:.1f}"
            )
        elif (
            heartbeat_age
            >= self.policy.heartbeat_warning_seconds
        ):
            severity = max(severity, 1)
            reasons.append(
                "Heartbeatが警告閾値を超えて停滞しています。 "
                f"age_seconds={heartbeat_age:.1f}"
            )

        if cycle_age is None:
            severity = max(severity, 1)
            reasons.append(
                "Trading Cycleがまだ記録されていません。"
            )
        elif (
            cycle_age
            >= self.policy.cycle_critical_seconds
        ):
            severity = max(severity, 2)
            reasons.append(
                "Trading Cycleが重大閾値を超えて停止しています。 "
                f"age_seconds={cycle_age:.1f}"
            )
        elif (
            cycle_age
            >= self.policy.cycle_warning_seconds
        ):
            severity = max(severity, 1)
            reasons.append(
                "Trading Cycleが警告閾値を超えて停滞しています。 "
                f"age_seconds={cycle_age:.1f}"
            )

        status = {
            0: RuntimeHealthStatus.HEALTHY,
            1: RuntimeHealthStatus.WARNING,
            2: RuntimeHealthStatus.CRITICAL,
        }[severity]

        return RuntimeHealthMonitorReport(
            status=status,
            checked_at=snapshot.checked_at,
            running=True,
            heartbeat_age_seconds=heartbeat_age,
            cycle_age_seconds=cycle_age,
            reasons=tuple(reasons),
        )

    @staticmethod
    def _age(
        checked_at,
        occurred_at,
    ) -> float | None:
        """確認日時からの経過秒数を返す。"""

        if occurred_at is None:
            return None

        return (
            checked_at - occurred_at
        ).total_seconds()
