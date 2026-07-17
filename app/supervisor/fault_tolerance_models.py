"""SupervisorとRecoveryを連携する耐障害性モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.live.recovery_models import RecoveryResult
from app.supervisor.supervisor_models import SupervisorSnapshot


class FaultToleranceDecision(StrEnum):
    """耐障害性フローの判定結果。"""

    NO_ACTION = "no_action"
    DEFERRED = "deferred"
    RECOVERED = "recovered"
    RECOVERY_FAILED = "recovery_failed"
    SAFE_STOP = "safe_stop"


@dataclass(frozen=True, slots=True)
class FaultTolerancePolicy:
    """自動復旧と安全停止に関する方針。"""

    maximum_consecutive_recovery_failures: int = 3
    continue_recovery_on_error: bool = True

    def __post_init__(self) -> None:
        """方針を検証する。"""

        if self.maximum_consecutive_recovery_failures <= 0:
            raise ValueError(
                "最大連続復旧失敗回数は0より大きい必要があります。"
            )


@dataclass(frozen=True, slots=True)
class FaultToleranceAttempt:
    """1回の耐障害性フロー実行結果。"""

    attempt_number: int
    checked_at: datetime
    decision: FaultToleranceDecision
    supervisor_before: SupervisorSnapshot
    supervisor_after: SupervisorSnapshot
    recovery_result: RecoveryResult | None
    consecutive_failure_count: int
    next_action_at: datetime | None
    message: str

    def __post_init__(self) -> None:
        """結果の整合性を検証する。"""

        message = self.message.strip()

        if self.attempt_number <= 0:
            raise ValueError(
                "試行番号は0より大きい必要があります。"
            )

        if self.checked_at.tzinfo is None:
            raise ValueError(
                "確認日時にはタイムゾーンが必要です。"
            )

        if self.consecutive_failure_count < 0:
            raise ValueError(
                "連続失敗回数は0以上である必要があります。"
            )

        if not message:
            raise ValueError(
                "耐障害性フローのメッセージが必要です。"
            )

        if (
            self.decision is FaultToleranceDecision.RECOVERED
            and self.recovery_result is None
        ):
            raise ValueError(
                "復旧成功結果にはRecovery結果が必要です。"
            )

        if (
            self.decision is FaultToleranceDecision.DEFERRED
            and self.next_action_at is None
        ):
            raise ValueError(
                "延期結果には次回実行日時が必要です。"
            )

        object.__setattr__(self, "message", message)

    @property
    def is_successful(self) -> bool:
        """正常終了または復旧成功か返す。"""

        return self.decision in {
            FaultToleranceDecision.NO_ACTION,
            FaultToleranceDecision.RECOVERED,
        }

    @property
    def requires_attention(self) -> bool:
        """運用者の確認が必要か返す。"""

        return self.decision in {
            FaultToleranceDecision.RECOVERY_FAILED,
            FaultToleranceDecision.SAFE_STOP,
        }
