"""バックテスト注文キューをBrokerへ送信し約定履歴を保存する。"""

from typing import Protocol
from dataclasses import dataclass
from enum import StrEnum

from app.backtest.order_queue import (
    BacktestOrderQueue,
    QueuedBacktestOrder,
)
from app.trading.order_broker_sync_service import (
    OrderBrokerSyncResult,
    OrderBrokerSyncService,
)
from app.trading.order_models import OrderStatus
from app.trading.trade_execution_models import (
    TradeExecution,
    TradeExecutionRecord,
)
from app.trading.trade_execution_repository import (
    DuplicateTradeExecutionError,
    TradeExecutionRepository,
)



class TradeExecutionObserver(Protocol):
    """新規保存された約定を受け取るObserver。"""

    def record(
        self,
        execution_record: TradeExecutionRecord,
    ) -> None:
        """新規約定を処理する。"""


class BacktestQueueExecutionDecision(StrEnum):
    """キュー注文の執行結果。"""

    TERMINAL = "terminal"
    ACTIVE = "active"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class BacktestQueueExecutionItemResult:
    """キュー内の1注文を執行した結果。"""

    decision: BacktestQueueExecutionDecision
    queued_order: QueuedBacktestOrder
    broker_sync_result: OrderBrokerSyncResult | None
    execution_record: TradeExecutionRecord | None
    message: str | None

    @property
    def order_id(self) -> str:
        """注文IDを返す。"""

        return self.queued_order.order_id

    @property
    def is_terminal(self) -> bool:
        """注文が終了状態になったか返す。"""

        return (
            self.decision
            is BacktestQueueExecutionDecision.TERMINAL
        )

    @property
    def is_active(self) -> bool:
        """注文がBroker上で継続中か返す。"""

        return (
            self.decision
            is BacktestQueueExecutionDecision.ACTIVE
        )

    @property
    def is_failed(self) -> bool:
        """執行に失敗したか返す。"""

        return (
            self.decision
            is BacktestQueueExecutionDecision.FAILED
        )


@dataclass(frozen=True, slots=True)
class BacktestQueueExecutionBatchResult:
    """注文キューの一括執行結果。"""

    items: tuple[
        BacktestQueueExecutionItemResult,
        ...
    ]

    @property
    def processed_count(self) -> int:
        """処理した注文件数を返す。"""

        return len(self.items)

    @property
    def terminal_count(self) -> int:
        """終了状態になった注文件数を返す。"""

        return sum(
            item.is_terminal
            for item in self.items
        )

    @property
    def active_count(self) -> int:
        """Broker上で継続中の注文件数を返す。"""

        return sum(
            item.is_active
            for item in self.items
        )

    @property
    def failed_count(self) -> int:
        """失敗した注文件数を返す。"""

        return sum(
            item.is_failed
            for item in self.items
        )

    @property
    def saved_execution_count(self) -> int:
        """保存した約定履歴件数を返す。"""

        return sum(
            item.execution_record is not None
            for item in self.items
        )

    @property
    def is_successful(self) -> bool:
        """失敗がないか返す。"""

        return self.failed_count == 0


class BacktestQueueExecutionService:
    """バックテスト注文キューとBroker・約定台帳を接続する。"""

    def __init__(
        self,
        *,
        order_queue: BacktestOrderQueue,
        broker_sync_service: OrderBrokerSyncService,
        execution_repository: TradeExecutionRepository,
        broker_name: str,
        commission_per_execution: float = 0.0,
        slippage_per_execution: float = 0.0,
        execution_observers: tuple[
            TradeExecutionObserver,
            ...,
        ] = (),
        continue_on_notification_error: bool = True,
    ) -> None:
        """必要な依存関係と約定コストを設定する。"""

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

        self.order_queue = order_queue
        self.broker_sync_service = broker_sync_service
        self.execution_repository = execution_repository
        self.broker_name = normalized_broker_name
        self.commission_per_execution = (
            commission_per_execution
        )
        self.slippage_per_execution = (
            slippage_per_execution
        )
        self.execution_observers = tuple(
            execution_observers
        )
        self.continue_on_notification_error = (
            continue_on_notification_error
        )

    def execute_next(
        self,
        *,
        continue_on_error: bool = False,
    ) -> BacktestQueueExecutionItemResult | None:
        """キュー先頭の注文をBrokerへ送信する。"""

        queued_order = self.order_queue.peek()

        if queued_order is None:
            return None

        try:
            sync_result = self.broker_sync_service.submit(
                queued_order.order_id,
                continue_on_error=False,
            )

            order_record = sync_result.order_record

            if order_record is None:
                raise RuntimeError(
                    "Broker同期結果に注文レコードがありません。 "
                    f"order_id={queued_order.order_id}"
                )

            execution_record = self._save_new_fill(
                queued_order=queued_order,
                sync_result=sync_result,
            )

            decision = (
                BacktestQueueExecutionDecision.TERMINAL
                if order_record.status.is_terminal
                else BacktestQueueExecutionDecision.ACTIVE
            )

            popped = self.order_queue.pop()

            if popped != queued_order:
                raise RuntimeError(
                    "注文キューの先頭が処理対象と一致しません。 "
                    f"order_id={queued_order.order_id}"
                )

            return BacktestQueueExecutionItemResult(
                decision=decision,
                queued_order=queued_order,
                broker_sync_result=sync_result,
                execution_record=execution_record,
                message=None,
            )

        except Exception as error:
            if not continue_on_error:
                raise

            popped = self.order_queue.pop()

            if popped != queued_order:
                raise RuntimeError(
                    "失敗注文をキューから削除できませんでした。 "
                    f"order_id={queued_order.order_id}"
                ) from error

            return BacktestQueueExecutionItemResult(
                decision=BacktestQueueExecutionDecision.FAILED,
                queued_order=queued_order,
                broker_sync_result=None,
                execution_record=None,
                message=str(error),
            )

    def execute_all(
        self,
        *,
        limit: int | None = None,
        continue_on_error: bool = True,
    ) -> BacktestQueueExecutionBatchResult:
        """FIFO順でキュー注文を指定件数まで執行する。"""

        if limit is not None and limit <= 0:
            raise ValueError(
                "処理件数は0より大きい必要があります。"
            )

        target_count = self.order_queue.count

        if limit is not None:
            target_count = min(
                target_count,
                limit,
            )

        results: list[
            BacktestQueueExecutionItemResult
        ] = []

        for _ in range(target_count):
            result = self.execute_next(
                continue_on_error=continue_on_error,
            )

            if result is None:
                break

            results.append(result)

        return BacktestQueueExecutionBatchResult(
            items=tuple(results),
        )

    def _save_new_fill(
        self,
        *,
        queued_order: QueuedBacktestOrder,
        sync_result: OrderBrokerSyncResult,
    ) -> TradeExecutionRecord | None:
        """Broker同期結果から未保存の約定数量を保存する。"""

        order_record = sync_result.order_record
        snapshot = sync_result.broker_snapshot

        if order_record is None or snapshot is None:
            return None

        if (
            snapshot.filled_quantity <= 0
            or snapshot.average_fill_price is None
        ):
            return None

        existing_records = (
            self.execution_repository.find_by_order(
                order_record.order_id
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

        if new_quantity <= 0:
            return None

        execution_id = (
            f"{snapshot.broker_order_id}:"
            f"{snapshot.filled_quantity}"
        )

        execution = TradeExecution(
            execution_id=execution_id,
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
                "queue_enqueued_at": (
                    queued_order.enqueued_at.isoformat()
                ),
            },
        )

        try:
            record = self.execution_repository.save(
                execution
            )
        except DuplicateTradeExecutionError:
            return self.execution_repository.get(
                execution_id
            )

        self._notify_execution_observers(
            record
        )

        return record

    def _notify_execution_observers(
        self,
        execution_record: TradeExecutionRecord,
    ) -> None:
        """新規約定をObserverへ通知する。"""

        for observer in self.execution_observers:
            try:
                observer.record(
                    execution_record
                )
            except Exception:
                if (
                    not self.continue_on_notification_error
                ):
                    raise
