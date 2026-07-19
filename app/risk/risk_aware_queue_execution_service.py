"""リスク判定に基づいて注文キューのBroker送信を制御する。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.backtest.queue_execution_service import (
    BacktestQueueExecutionBatchResult,
)


class QueueExecutionRiskState(Protocol):
    """注文執行可否の判定に必要なRisk結果。"""

    @property
    def allows_new_entries(self) -> bool:
        """新規エントリーを許可するか返す。"""

    @property
    def is_blocked(self) -> bool:
        """リスク判定が停止状態か返す。"""


class QueueExecutionDelegate(Protocol):
    """実際の注文キュー執行処理。"""

    def execute_all(
        self,
        *,
        limit: int | None = None,
        continue_on_error: bool = True,
    ) -> BacktestQueueExecutionBatchResult:
        """FIFO順でキュー注文を執行する。"""


class RiskAwareQueueExecutionDecision(StrEnum):
    """リスク判定を含む注文キュー執行判断。"""

    EXECUTED = "executed"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class RiskAwareQueueExecutionResult:
    """リスク判定を含む注文キュー執行結果。"""

    decision: RiskAwareQueueExecutionDecision
    execution_result: BacktestQueueExecutionBatchResult | None
    message: str | None = None

    def __post_init__(self) -> None:
        """判断とBroker執行結果の整合性を検証する。"""

        normalized_message = (
            None
            if self.message is None
            else self.message.strip() or None
        )

        if (
            self.decision
            is RiskAwareQueueExecutionDecision.EXECUTED
            and self.execution_result is None
        ):
            raise ValueError(
                "EXECUTED結果には注文執行結果が必要です。"
            )

        if (
            self.decision
            is RiskAwareQueueExecutionDecision.BLOCKED
            and self.execution_result is not None
        ):
            raise ValueError(
                "BLOCKED結果には注文執行結果を設定できません。"
            )

        if (
            self.decision
            is RiskAwareQueueExecutionDecision.BLOCKED
            and normalized_message is None
        ):
            raise ValueError(
                "BLOCKED結果には停止理由が必要です。"
            )

        object.__setattr__(
            self,
            "message",
            normalized_message,
        )

    @property
    def was_executed(self) -> bool:
        """Broker執行処理を呼び出したか返す。"""

        return (
            self.decision
            is RiskAwareQueueExecutionDecision.EXECUTED
        )

    @property
    def was_blocked(self) -> bool:
        """リスク制御によりBroker送信を停止したか返す。"""

        return (
            self.decision
            is RiskAwareQueueExecutionDecision.BLOCKED
        )

    @property
    def processed_count(self) -> int:
        """処理した注文件数を返す。"""

        if self.execution_result is None:
            return 0

        return self.execution_result.processed_count

    @property
    def terminal_count(self) -> int:
        """終了状態になった注文件数を返す。"""

        if self.execution_result is None:
            return 0

        return self.execution_result.terminal_count

    @property
    def active_count(self) -> int:
        """Broker上で継続中の注文件数を返す。"""

        if self.execution_result is None:
            return 0

        return self.execution_result.active_count

    @property
    def failed_count(self) -> int:
        """執行に失敗した注文件数を返す。"""

        if self.execution_result is None:
            return 0

        return self.execution_result.failed_count

    @property
    def saved_execution_count(self) -> int:
        """保存した約定履歴件数を返す。"""

        if self.execution_result is None:
            return 0

        return self.execution_result.saved_execution_count

    @property
    def is_successful(self) -> bool:
        """リスク停止またはBroker執行失敗がないか返す。"""

        if self.was_blocked:
            return False

        if self.execution_result is None:
            return False

        return self.execution_result.is_successful


class RiskAwareQueueExecutionService:
    """Risk結果を注文キュー執行前のゲートとして適用する。"""

    def __init__(
        self,
        *,
        execution_service: QueueExecutionDelegate,
    ) -> None:
        """実際の注文キュー執行サービスを設定する。"""

        self.execution_service = execution_service
        self._last_result: RiskAwareQueueExecutionResult | None = None
        self._execution_count = 0
        self._blocked_count = 0

    @property
    def last_result(
        self,
    ) -> RiskAwareQueueExecutionResult | None:
        """最新のゲート判定結果を返す。"""

        return self._last_result

    @property
    def execution_count(self) -> int:
        """Broker執行処理を呼び出した回数を返す。"""

        return self._execution_count

    @property
    def blocked_count(self) -> int:
        """リスク制御により停止した回数を返す。"""

        return self._blocked_count

    def execute_all(
        self,
        *,
        risk_result: QueueExecutionRiskState,
        limit: int | None = None,
        continue_on_error: bool = True,
    ) -> RiskAwareQueueExecutionResult:
        """Risk判定が許可した場合だけ注文キューを執行する。"""

        if limit is not None and limit <= 0:
            raise ValueError(
                "処理件数は0より大きい必要があります。"
            )

        self._validate_risk_state(risk_result)

        if risk_result.is_blocked:
            result = RiskAwareQueueExecutionResult(
                decision=(
                    RiskAwareQueueExecutionDecision.BLOCKED
                ),
                execution_result=None,
                message=(
                    "Risk Engineが新規エントリーを停止しているため、"
                    "注文をBrokerへ送信しませんでした。"
                ),
            )
            self._last_result = result
            self._blocked_count += 1
            return result

        execution_result = self.execution_service.execute_all(
            limit=limit,
            continue_on_error=continue_on_error,
        )
        result = RiskAwareQueueExecutionResult(
            decision=(
                RiskAwareQueueExecutionDecision.EXECUTED
            ),
            execution_result=execution_result,
            message=None,
        )
        self._last_result = result
        self._execution_count += 1

        return result

    @staticmethod
    def _validate_risk_state(
        risk_result: QueueExecutionRiskState,
    ) -> None:
        """Risk結果のエントリー可否と停止状態を検証する。"""

        if (
            risk_result.allows_new_entries
            == risk_result.is_blocked
        ):
            raise ValueError(
                "Risk結果のallows_new_entriesと"
                "is_blockedが矛盾しています。"
            )
