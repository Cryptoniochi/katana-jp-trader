"""連敗停止機能の判定を行うサービス。"""

from __future__ import annotations

from app.risk.consecutive_loss_models import (
    ConsecutiveLossEvaluation,
    ConsecutiveLossPolicy,
    ConsecutiveLossReason,
    ConsecutiveLossSnapshot,
    ConsecutiveLossStatus,
)


class ConsecutiveLossService:
    """連敗数を評価し、新規エントリー可否を判定する。"""

    def __init__(
        self,
        *,
        policy: ConsecutiveLossPolicy,
    ) -> None:
        """連敗停止Policyを設定する。"""

        self.policy = policy

    def evaluate(
        self,
        snapshot: ConsecutiveLossSnapshot,
    ) -> ConsecutiveLossEvaluation:
        """Snapshotを評価して連敗停止判定を返す。"""

        status, reason = self._determine_status(
            snapshot=snapshot,
        )

        remaining_losses_before_block = max(
            0,
            self.policy.max_consecutive_losses
            - snapshot.consecutive_losses,
        )

        return ConsecutiveLossEvaluation(
            trading_date=snapshot.trading_date,
            status=status,
            reason=reason,
            consecutive_losses=snapshot.consecutive_losses,
            warning_consecutive_losses=(
                self.policy.warning_consecutive_losses
            ),
            max_consecutive_losses=(
                self.policy.max_consecutive_losses
            ),
            remaining_losses_before_block=(
                remaining_losses_before_block
            ),
            last_trade_pnl=snapshot.last_trade_pnl,
            evaluated_at=snapshot.evaluated_at,
            metadata={
                "manual_blocked": snapshot.manual_blocked,
            },
        )

    def allows_new_entries(
        self,
        snapshot: ConsecutiveLossSnapshot,
    ) -> bool:
        """新規エントリーを許可するか返す。"""

        return self.evaluate(
            snapshot
        ).allows_new_entries

    def is_blocked(
        self,
        snapshot: ConsecutiveLossSnapshot,
    ) -> bool:
        """新規エントリー停止状態か返す。"""

        return self.evaluate(
            snapshot
        ).is_blocked

    def _determine_status(
        self,
        *,
        snapshot: ConsecutiveLossSnapshot,
    ) -> tuple[
        ConsecutiveLossStatus,
        ConsecutiveLossReason,
    ]:
        """連敗数と手動停止状態から判定を返す。"""

        if snapshot.manual_blocked:
            return (
                ConsecutiveLossStatus.BLOCKED,
                ConsecutiveLossReason.MANUALLY_BLOCKED,
            )

        if (
            snapshot.consecutive_losses
            >= self.policy.max_consecutive_losses
        ):
            return (
                ConsecutiveLossStatus.BLOCKED,
                ConsecutiveLossReason.LOSS_LIMIT_REACHED,
            )

        if (
            snapshot.consecutive_losses
            >= self.policy.warning_consecutive_losses
        ):
            return (
                ConsecutiveLossStatus.WARNING,
                ConsecutiveLossReason.WARNING_THRESHOLD_REACHED,
            )

        return (
            ConsecutiveLossStatus.ACTIVE,
            ConsecutiveLossReason.WITHIN_LIMIT,
        )
