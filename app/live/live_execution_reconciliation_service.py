"""Broker注文を再照会し、増分約定を台帳へ保存する。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.trading.order_broker_sync_service import (
    OrderBrokerSyncResult,
)
from app.trading.order_models import (
    OrderStatus,
    TradeOrderRecord,
)
from app.trading.trade_execution_models import (
    TradeExecution,
    TradeExecutionRecord,
)


class LiveExecutionReconciliationDecision(StrEnum):
    """1注文の約定照合結果。"""

    SAVED = "saved"
    UNCHANGED = "unchanged"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class LiveExecutionReconciliationItem:
    """1注文の増分約定照合結果。"""

    order_id: str
    decision: LiveExecutionReconciliationDecision
    order_record: TradeOrderRecord | None
    execution_record: TradeExecutionRecord | None
    new_filled_quantity: int
    message: str | None = None

    def __post_init__(self) -> None:
        """結果の整合性を検証する。"""

        normalized_order_id = self.order_id.strip()

        if not normalized_order_id:
            raise ValueError(
                "注文IDを指定してください。"
            )

        if self.new_filled_quantity < 0:
            raise ValueError(
                "新規約定数量は0以上である必要があります。"
            )

        if (
            self.decision
            is LiveExecutionReconciliationDecision.SAVED
            and (
                self.execution_record is None
                or self.new_filled_quantity <= 0
            )
        ):
            raise ValueError(
                "保存結果には約定履歴と正の約定数量が必要です。"
            )

        if (
            self.decision
            is LiveExecutionReconciliationDecision.UNCHANGED
            and (
                self.execution_record is not None
                or self.new_filled_quantity != 0
            )
        ):
            raise ValueError(
                "変更なし結果には約定履歴を設定できません。"
            )

        if (
            self.decision
            is LiveExecutionReconciliationDecision.FAILED
            and not (self.message or "").strip()
        ):
            raise ValueError(
                "失敗結果にはメッセージが必要です。"
            )

        object.__setattr__(
            self,
            "order_id",
            normalized_order_id,
        )

    @property
    def was_saved(self) -> bool:
        """増分約定を保存したか返す。"""

        return (
            self.decision
            is LiveExecutionReconciliationDecision.SAVED
        )

    @property
    def is_failed(self) -> bool:
        """照合に失敗したか返す。"""

        return (
            self.decision
            is LiveExecutionReconciliationDecision.FAILED
        )


@dataclass(frozen=True, slots=True)
class LiveExecutionReconciliationBatchResult:
    """複数注文の約定照合結果。"""

    items: tuple[
        LiveExecutionReconciliationItem,
        ...
    ]

    @property
    def order_count(self) -> int:
        """照合注文件数を返す。"""

        return len(self.items)

    @property
    def saved_count(self) -> int:
        """保存約定件数を返す。"""

        return sum(
            item.was_saved
            for item in self.items
        )

    @property
    def failed_count(self) -> int:
        """失敗件数を返す。"""

        return sum(
            item.is_failed
            for item in self.items
        )

    @property
    def new_filled_quantity(self) -> int:
        """新規約定数量の合計を返す。"""

        return sum(
            item.new_filled_quantity
            for item in self.items
        )


class BrokerOrderRefresher(Protocol):
    """Broker注文状態の再照会処理。"""

    def refresh(
        self,
        order_id: str,
        *,
        continue_on_error: bool = False,
    ) -> OrderBrokerSyncResult:
        """注文をBroker最新状態へ同期する。"""


class ExecutionLedger(Protocol):
    """増分約定の検索・保存処理。"""

    def find_by_order(
        self,
        order_id: str,
    ) -> list[TradeExecutionRecord]:
        """注文に紐づく約定履歴を返す。"""

    def save(
        self,
        execution: TradeExecution,
    ) -> TradeExecutionRecord:
        """約定を保存する。"""


class LiveExecutionReconciliationService:
    """Broker累積約定数量をローカル約定台帳へ増分反映する。"""

    def __init__(
        self,
        *,
        broker_sync_service: BrokerOrderRefresher,
        execution_repository: ExecutionLedger,
        broker_name: str,
        commission_per_execution: float = 0.0,
        slippage_per_execution: float = 0.0,
    ) -> None:
        """依存関係と約定コストを設定する。"""

        normalized_broker_name = broker_name.strip()

        if not normalized_broker_name:
            raise ValueError(
                "Broker名を指定してください。"
            )

        if commission_per_execution < 0:
            raise ValueError(
                "約定手数料は0以上である必要があります。"
            )

        if slippage_per_execution < 0:
            raise ValueError(
                "約定スリッページは0以上である必要があります。"
            )

        self.broker_sync_service = broker_sync_service
        self.execution_repository = execution_repository
        self.broker_name = normalized_broker_name
        self.commission_per_execution = (
            commission_per_execution
        )
        self.slippage_per_execution = (
            slippage_per_execution
        )

    def reconcile(
        self,
        order_id: str,
        *,
        continue_on_error: bool = False,
    ) -> LiveExecutionReconciliationItem:
        """1注文を再照会し、未保存の約定数量だけ保存する。"""

        normalized_order_id = order_id.strip()

        if not normalized_order_id:
            raise ValueError(
                "注文IDを指定してください。"
            )

        try:
            sync_result = self.broker_sync_service.refresh(
                normalized_order_id,
                continue_on_error=False,
            )
            order_record = sync_result.order_record
            snapshot = sync_result.broker_snapshot

            if order_record is None or snapshot is None:
                raise RuntimeError(
                    "Broker同期結果に注文情報がありません。 "
                    f"order_id={normalized_order_id}"
                )

            existing_records = (
                self.execution_repository.find_by_order(
                    normalized_order_id
                )
            )
            recorded_quantity = sum(
                record.execution.quantity
                for record in existing_records
            )
            new_quantity = (
                snapshot.filled_quantity
                - recorded_quantity
            )

            if new_quantity < 0:
                raise RuntimeError(
                    "保存済み約定数量がBroker累積約定数量を"
                    "上回っています。 "
                    f"order_id={normalized_order_id} "
                    f"recorded={recorded_quantity} "
                    f"broker={snapshot.filled_quantity}"
                )

            if new_quantity == 0:
                return LiveExecutionReconciliationItem(
                    order_id=normalized_order_id,
                    decision=(
                        LiveExecutionReconciliationDecision.UNCHANGED
                    ),
                    order_record=order_record,
                    execution_record=None,
                    new_filled_quantity=0,
                    message=None,
                )

            if snapshot.average_fill_price is None:
                raise RuntimeError(
                    "約定済み注文に平均約定価格がありません。 "
                    f"order_id={normalized_order_id}"
                )

            execution = TradeExecution(
                execution_id=(
                    f"{snapshot.broker_order_id}:"
                    f"{snapshot.filled_quantity}"
                ),
                signal_id=order_record.signal_id,
                order_id=order_record.order_id,
                broker_order_id=snapshot.broker_order_id,
                code=order_record.code,
                side=order_record.order.side,
                quantity=new_quantity,
                execution_price=snapshot.average_fill_price,
                executed_at=snapshot.updated_at,
                broker_name=self.broker_name,
                commission=self.commission_per_execution,
                slippage=self.slippage_per_execution,
                metadata={
                    "cumulative_filled_quantity": (
                        snapshot.filled_quantity
                    ),
                    "order_status": snapshot.status.value,
                    "reconciliation": "live",
                },
            )
            saved = self.execution_repository.save(
                execution
            )

            return LiveExecutionReconciliationItem(
                order_id=normalized_order_id,
                decision=(
                    LiveExecutionReconciliationDecision.SAVED
                ),
                order_record=order_record,
                execution_record=saved,
                new_filled_quantity=new_quantity,
                message=None,
            )

        except Exception as error:
            if not continue_on_error:
                raise

            return LiveExecutionReconciliationItem(
                order_id=normalized_order_id,
                decision=(
                    LiveExecutionReconciliationDecision.FAILED
                ),
                order_record=None,
                execution_record=None,
                new_filled_quantity=0,
                message=str(error),
            )

    def reconcile_many(
        self,
        order_ids: tuple[str, ...],
        *,
        continue_on_error: bool = False,
    ) -> LiveExecutionReconciliationBatchResult:
        """複数注文を指定順に照合する。"""

        return LiveExecutionReconciliationBatchResult(
            items=tuple(
                self.reconcile(
                    order_id,
                    continue_on_error=continue_on_error,
                )
                for order_id in order_ids
            )
        )
