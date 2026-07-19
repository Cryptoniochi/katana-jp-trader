"""Kill Switchの統合判定を行うサービス。"""

from __future__ import annotations

from app.risk.kill_switch_models import (
    KillSwitchEvaluation,
    KillSwitchReason,
    KillSwitchSnapshot,
    KillSwitchStatus,
)


class KillSwitchService:
    """複数の安全条件を統合し、新規エントリー可否を判定する。"""

    def evaluate(
        self,
        snapshot: KillSwitchSnapshot,
    ) -> KillSwitchEvaluation:
        """Snapshotを評価してKill Switch判定を返す。"""

        status, reason = self._determine_status(
            snapshot=snapshot,
        )

        return KillSwitchEvaluation(
            status=status,
            reason=reason,
            evaluated_at=snapshot.evaluated_at,
            metadata={
                "manual_blocked": snapshot.manual_blocked,
                "daily_loss_blocked": snapshot.daily_loss_blocked,
                "consecutive_loss_blocked": (
                    snapshot.consecutive_loss_blocked
                ),
                "runtime_health_ok": snapshot.runtime_health_ok,
                "heartbeat_alive": snapshot.heartbeat_alive,
                "broker_available": snapshot.broker_available,
            },
        )

    def allows_new_entries(
        self,
        snapshot: KillSwitchSnapshot,
    ) -> bool:
        """新規エントリーを許可するか返す。"""

        return self.evaluate(
            snapshot
        ).allows_new_entries

    def is_blocked(
        self,
        snapshot: KillSwitchSnapshot,
    ) -> bool:
        """Kill Switchが停止状態か返す。"""

        return self.evaluate(
            snapshot
        ).is_blocked

    @staticmethod
    def _determine_status(
        *,
        snapshot: KillSwitchSnapshot,
    ) -> tuple[
        KillSwitchStatus,
        KillSwitchReason,
    ]:
        """各安全条件を優先順位順に評価する。"""

        if snapshot.manual_blocked:
            return (
                KillSwitchStatus.BLOCKED,
                KillSwitchReason.MANUAL,
            )

        if snapshot.daily_loss_blocked:
            return (
                KillSwitchStatus.BLOCKED,
                KillSwitchReason.DAILY_LOSS,
            )

        if snapshot.consecutive_loss_blocked:
            return (
                KillSwitchStatus.BLOCKED,
                KillSwitchReason.CONSECUTIVE_LOSS,
            )

        if not snapshot.runtime_health_ok:
            return (
                KillSwitchStatus.BLOCKED,
                KillSwitchReason.RUNTIME_HEALTH,
            )

        if not snapshot.heartbeat_alive:
            return (
                KillSwitchStatus.BLOCKED,
                KillSwitchReason.HEARTBEAT,
            )

        if not snapshot.broker_available:
            return (
                KillSwitchStatus.BLOCKED,
                KillSwitchReason.BROKER,
            )

        return (
            KillSwitchStatus.ACTIVE,
            KillSwitchReason.NONE,
        )
