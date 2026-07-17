"""ライブ運転再開時の復旧結果モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.broker.broker_health_models import BrokerHealthCheckResult
from app.live.live_execution_reconciliation_service import (
    LiveExecutionReconciliationBatchResult,
)
from app.trading.portfolio_audit_models import PortfolioAuditReport


class RecoveryStepStatus(StrEnum):
    """復旧ステップの終了状態。"""

    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class RecoveryStatus(StrEnum):
    """復旧処理全体の終了状態。"""

    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RecoveryStepResult:
    """1つの復旧ステップ結果。"""

    name: str
    status: RecoveryStepStatus
    message: str | None = None

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        normalized_message = (
            None
            if self.message is None
            else self.message.strip()
        )

        if not normalized_name:
            raise ValueError(
                "復旧ステップ名を指定してください。"
            )

        if (
            self.status is RecoveryStepStatus.FAILED
            and not normalized_message
        ):
            raise ValueError(
                "失敗ステップにはメッセージが必要です。"
            )

        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(
            self,
            "message",
            normalized_message or None,
        )

    @property
    def is_failed(self) -> bool:
        return self.status is RecoveryStepStatus.FAILED


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    """起動時復旧処理の全体結果。"""

    status: RecoveryStatus
    steps: tuple[RecoveryStepResult, ...]
    health_result: BrokerHealthCheckResult | None
    execution_result: (
        LiveExecutionReconciliationBatchResult | None
    )
    portfolio_audit_report: PortfolioAuditReport | None

    @property
    def failed_step_count(self) -> int:
        return sum(step.is_failed for step in self.steps)

    @property
    def is_successful(self) -> bool:
        return self.status is RecoveryStatus.COMPLETED

    @property
    def has_errors(self) -> bool:
        return self.failed_step_count > 0
