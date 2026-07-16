"""未処理シグナルを注文へ変換しBrokerへ執行するExecution Engine。"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.trading.order_broker_sync_service import (
    OrderBrokerSyncResult,
)
from app.trading.order_models import (
    OrderStatus,
    OrderType,
    TradeOrderRecord,
)
from app.trading.order_service import (
    SignalOrderCreationResult,
)
from app.trading.signal_models import (
    TradeSignalRecord,
)


class PendingSignalReader(Protocol):
    """未処理シグナル取得処理のインターフェース。"""

    def list_pending(
        self,
        *,
        limit: int = 100,
        code: str | None = None,
        strategy_name: str | None = None,
    ) -> list[TradeSignalRecord]:
        """未処理シグナルを返す。"""


class SignalOrderCreator(Protocol):
    """シグナルから注文を作成する処理のインターフェース。"""

    def create_from_signal(
        self,
        signal_id: str,
        *,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
        continue_on_error: bool = False,
    ) -> SignalOrderCreationResult:
        """シグナルから注文を作成する。"""


class OrderBrokerSynchronizer(Protocol):
    """注文をBrokerへ送信・同期する処理のインターフェース。"""

    def submit(
        self,
        order_id: str,
        *,
        continue_on_error: bool = False,
    ) -> OrderBrokerSyncResult:
        """注文をBrokerへ送信して状態を同期する。"""


class ExecutionDecision(StrEnum):
    """1件のシグナルに対する執行結果。"""

    EXECUTED = "executed"
    ACTIVE = "active"
    TERMINAL = "terminal"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ExecutionItemResult:
    """1件のシグナルを注文執行した結果。"""

    decision: ExecutionDecision
    signal_id: str
    order_id: str | None

    signal_record: TradeSignalRecord | None
    order_record: TradeOrderRecord | None

    order_creation_result: (
        SignalOrderCreationResult | None
    )
    broker_sync_result: (
        OrderBrokerSyncResult | None
    )

    message: str | None

    @property
    def is_executed(self) -> bool:
        """Brokerへの送信・同期まで完了したか返す。"""

        return self.decision in {
            ExecutionDecision.EXECUTED,
            ExecutionDecision.ACTIVE,
            ExecutionDecision.TERMINAL,
        }

    @property
    def is_active(self) -> bool:
        """注文がBroker上で継続中か返す。"""

        return (
            self.decision
            is ExecutionDecision.ACTIVE
        )

    @property
    def is_terminal(self) -> bool:
        """注文が終了状態になったか返す。"""

        return (
            self.decision
            is ExecutionDecision.TERMINAL
        )

    @property
    def is_failed(self) -> bool:
        """処理に失敗したか返す。"""

        return (
            self.decision
            is ExecutionDecision.FAILED
        )


@dataclass(frozen=True, slots=True)
class ExecutionBatchResult:
    """Execution Engineの一括処理結果。"""

    items: tuple[
        ExecutionItemResult,
        ...
    ]

    @property
    def input_count(self) -> int:
        """処理対象シグナル数を返す。"""

        return len(
            self.items
        )

    @property
    def executed_count(self) -> int:
        """Broker同期まで完了した件数を返す。"""

        return sum(
            item.is_executed
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
    def terminal_count(self) -> int:
        """終了状態になった注文件数を返す。"""

        return sum(
            item.is_terminal
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
    def order_records(
        self,
    ) -> tuple[
        TradeOrderRecord,
        ...
    ]:
        """取得できた注文レコード一覧を返す。"""

        return tuple(
            item.order_record
            for item in self.items
            if item.order_record is not None
        )

    @property
    def is_successful(self) -> bool:
        """失敗がないか返す。"""

        return self.failed_count == 0


class ExecutionEngine:
    """未処理シグナルを順番に注文執行する。"""

    def __init__(
        self,
        *,
        signal_repository: PendingSignalReader,
        order_service: SignalOrderCreator,
        broker_sync_service: OrderBrokerSynchronizer,
    ) -> None:
        """必要なRepositoryとサービスを設定する。"""

        self.signal_repository = signal_repository
        self.order_service = order_service
        self.broker_sync_service = broker_sync_service

    def run_pending(
        self,
        *,
        limit: int = 100,
        code: str | None = None,
        strategy_name: str | None = None,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
        continue_on_error: bool = True,
    ) -> ExecutionBatchResult:
        """未処理シグナルを古い順に注文執行する。"""

        if limit <= 0:
            raise ValueError(
                "処理件数は0より大きい必要があります。"
            )

        pending_signals = (
            self.signal_repository.list_pending(
                limit=limit,
                code=code,
                strategy_name=strategy_name,
            )
        )

        sorted_signals = sorted(
            pending_signals,
            key=lambda record: (
                record.signal.generated_at,
                record.signal_id,
            ),
        )

        results: list[
            ExecutionItemResult
        ] = []

        for signal_record in sorted_signals:
            try:
                item_result = self.execute_signal(
                    signal_record.signal_id,
                    order_type=order_type,
                    limit_price=limit_price,
                    stop_price=stop_price,
                )

            except Exception as error:
                if not continue_on_error:
                    raise

                item_result = ExecutionItemResult(
                    decision=ExecutionDecision.FAILED,
                    signal_id=(
                        signal_record.signal_id
                    ),
                    order_id=None,
                    signal_record=signal_record,
                    order_record=None,
                    order_creation_result=None,
                    broker_sync_result=None,
                    message=str(error),
                )

            results.append(
                item_result
            )

        return ExecutionBatchResult(
            items=tuple(
                results
            ),
        )

    def execute_signal(
        self,
        signal_id: str,
        *,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
    ) -> ExecutionItemResult:
        """指定シグナルを注文へ変換してBrokerへ送信する。"""

        normalized_signal_id = signal_id.strip()

        if not normalized_signal_id:
            raise ValueError(
                "シグナルIDを指定してください。"
            )

        creation_result = (
            self.order_service.create_from_signal(
                normalized_signal_id,
                order_type=order_type,
                limit_price=limit_price,
                stop_price=stop_price,
                continue_on_error=False,
            )
        )

        if creation_result.order_record is None:
            raise RuntimeError(
                "注文作成結果に注文レコードがありません。 "
                f"signal_id={normalized_signal_id}"
            )

        order_id = (
            creation_result
            .order_record
            .order_id
        )

        sync_result = (
            self.broker_sync_service.submit(
                order_id,
                continue_on_error=False,
            )
        )

        if sync_result.order_record is None:
            raise RuntimeError(
                "Broker同期結果に注文レコードがありません。 "
                f"signal_id={normalized_signal_id} "
                f"order_id={order_id}"
            )

        order_record = sync_result.order_record

        decision = self._resolve_decision(
            order_record
        )

        return ExecutionItemResult(
            decision=decision,
            signal_id=normalized_signal_id,
            order_id=order_id,
            signal_record=(
                creation_result.signal_record
            ),
            order_record=order_record,
            order_creation_result=creation_result,
            broker_sync_result=sync_result,
            message=None,
        )

    @staticmethod
    def _resolve_decision(
        order_record: TradeOrderRecord,
    ) -> ExecutionDecision:
        """注文状態からExecution結果を決定する。"""

        if order_record.status.is_terminal:
            return ExecutionDecision.TERMINAL

        if order_record.status in {
            OrderStatus.QUEUED,
            OrderStatus.SENT,
            OrderStatus.PARTIALLY_FILLED,
        }:
            return ExecutionDecision.ACTIVE

        return ExecutionDecision.EXECUTED