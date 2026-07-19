"""日次損失制限の判定を行うサービス。"""

from __future__ import annotations

from app.risk.daily_loss_models import (
    DailyLossEvaluation,
    DailyLossPolicy,
    DailyLossReason,
    DailyLossSnapshot,
    DailyLossStatus,
)


class DailyLossService:
    """日次損益を評価し、新規エントリー可否を判定する。"""

    def __init__(
        self,
        *,
        policy: DailyLossPolicy,
    ) -> None:
        """日次損失制限Policyを設定する。"""

        self.policy = policy

    def evaluate(
        self,
        snapshot: DailyLossSnapshot,
    ) -> DailyLossEvaluation:
        """Snapshotを評価して日次損失判定を返す。"""

        total_pnl = snapshot.total_pnl
        total_loss = snapshot.total_loss
        remaining_loss_capacity = max(
            0.0,
            self.policy.max_daily_loss - total_loss,
        )

        status, reason = self._determine_status(
            snapshot=snapshot,
            total_loss=total_loss,
        )

        return DailyLossEvaluation(
            trading_date=snapshot.trading_date,
            status=status,
            reason=reason,
            realized_pnl=snapshot.realized_pnl,
            unrealized_pnl=snapshot.unrealized_pnl,
            total_pnl=total_pnl,
            total_loss=total_loss,
            max_daily_loss=self.policy.max_daily_loss,
            warning_loss=self.policy.warning_loss,
            remaining_loss_capacity=remaining_loss_capacity,
            evaluated_at=snapshot.evaluated_at,
            metadata={
                "manual_blocked": snapshot.manual_blocked,
                "warning_ratio": self.policy.warning_ratio,
            },
        )

    def allows_new_entries(
        self,
        snapshot: DailyLossSnapshot,
    ) -> bool:
        """新規エントリーを許可するか返す。"""

        return self.evaluate(
            snapshot
        ).allows_new_entries

    def is_blocked(
        self,
        snapshot: DailyLossSnapshot,
    ) -> bool:
        """新規エントリー停止状態か返す。"""

        return self.evaluate(
            snapshot
        ).is_blocked

    def _determine_status(
        self,
        *,
        snapshot: DailyLossSnapshot,
        total_loss: float,
    ) -> tuple[DailyLossStatus, DailyLossReason]:
        """損失額と手動停止状態から判定を返す。"""

        if snapshot.manual_blocked:
            return (
                DailyLossStatus.BLOCKED,
                DailyLossReason.MANUALLY_BLOCKED,
            )

        if total_loss >= self.policy.max_daily_loss:
            return (
                DailyLossStatus.BLOCKED,
                DailyLossReason.LOSS_LIMIT_REACHED,
            )

        if total_loss >= self.policy.warning_loss:
            return (
                DailyLossStatus.WARNING,
                DailyLossReason.WARNING_THRESHOLD_REACHED,
            )

        return (
            DailyLossStatus.ACTIVE,
            DailyLossReason.WITHIN_LIMIT,
        )
