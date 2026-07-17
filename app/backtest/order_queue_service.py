"""バックテストシグナルを注文へ変換してキューへ登録する。"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Callable, Protocol

from app.backtest.order_queue import (
    BacktestOrderQueue,
    DuplicateQueuedOrderError,
    QueuedBacktestOrder,
)
from app.trading.order_models import (
    OrderType,
    TradeOrderRecord,
)
from app.trading.order_service import SignalOrderService
from app.trading.signal_models import TradeSignal
from app.trading.signal_repository import DuplicateSignalError


class SignalWriter(Protocol):
    """シグナル保存処理のインターフェース。"""

    def save(self, signal: TradeSignal):
        """シグナルを保存する。"""


class BacktestOrderQueueDecision(StrEnum):
    """1件のシグナル処理結果。"""

    ENQUEUED = "enqueued"
    EXISTING = "existing"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class BacktestOrderQueueResult:
    """シグナルからキュー登録までの処理結果。"""

    decision: BacktestOrderQueueDecision
    signal: TradeSignal
    order_record: TradeOrderRecord | None
    queued_order: QueuedBacktestOrder | None
    message: str | None

    @property
    def was_enqueued(self) -> bool:
        """新しくキューへ登録したか返す。"""

        return self.decision is BacktestOrderQueueDecision.ENQUEUED

    @property
    def was_existing(self) -> bool:
        """既存注文または既存キューを再利用したか返す。"""

        return self.decision is BacktestOrderQueueDecision.EXISTING

    @property
    def is_failed(self) -> bool:
        """処理に失敗したか返す。"""

        return self.decision is BacktestOrderQueueDecision.FAILED


class BacktestOrderQueueService:
    """シグナル保存・注文作成・キュー登録をまとめる。"""

    def __init__(
        self,
        *,
        signal_repository: SignalWriter,
        order_service: SignalOrderService,
        order_queue: BacktestOrderQueue,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """必要な依存関係と時計を設定する。"""

        self.signal_repository = signal_repository
        self.order_service = order_service
        self.order_queue = order_queue
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def enqueue_signal(
        self,
        signal: TradeSignal,
        *,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
        continue_on_error: bool = False,
    ) -> BacktestOrderQueueResult:
        """1件のシグナルを注文へ変換してキューへ登録する。"""

        try:
            try:
                self.signal_repository.save(signal)
            except DuplicateSignalError:
                pass

            creation_result = self.order_service.create_from_signal(
                signal.signal_id,
                order_type=order_type,
                limit_price=limit_price,
                stop_price=stop_price,
            )

            order_record = creation_result.order_record

            if order_record is None:
                raise RuntimeError(
                    "注文作成結果に注文レコードがありません。 "
                    f"signal_id={signal.signal_id}"
                )

            if self.order_queue.contains(order_record.order_id):
                return BacktestOrderQueueResult(
                    decision=BacktestOrderQueueDecision.EXISTING,
                    signal=signal,
                    order_record=order_record,
                    queued_order=self.order_queue.peek()
                    if self.order_queue.count == 1
                    else next(
                        item
                        for item in self.order_queue.snapshot()
                        if item.order_id == order_record.order_id
                    ),
                    message="既存のキュー済み注文を再利用しました。",
                )

            queued_order = QueuedBacktestOrder(
                order_record=order_record,
                enqueued_at=self._current_time(),
            )

            try:
                self.order_queue.enqueue(queued_order)
            except DuplicateQueuedOrderError:
                existing = next(
                    item
                    for item in self.order_queue.snapshot()
                    if item.order_id == order_record.order_id
                )

                return BacktestOrderQueueResult(
                    decision=BacktestOrderQueueDecision.EXISTING,
                    signal=signal,
                    order_record=order_record,
                    queued_order=existing,
                    message="既存のキュー済み注文を再利用しました。",
                )

            return BacktestOrderQueueResult(
                decision=BacktestOrderQueueDecision.ENQUEUED,
                signal=signal,
                order_record=order_record,
                queued_order=queued_order,
                message=None,
            )

        except Exception as error:
            if not continue_on_error:
                raise

            return BacktestOrderQueueResult(
                decision=BacktestOrderQueueDecision.FAILED,
                signal=signal,
                order_record=None,
                queued_order=None,
                message=str(error),
            )

    def enqueue_signals(
        self,
        signals: tuple[TradeSignal, ...],
        *,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
        continue_on_error: bool = False,
    ) -> tuple[BacktestOrderQueueResult, ...]:
        """複数シグナルを受け取った順番で処理する。"""

        return tuple(
            self.enqueue_signal(
                signal,
                order_type=order_type,
                limit_price=limit_price,
                stop_price=stop_price,
                continue_on_error=continue_on_error,
            )
            for signal in signals
        )

    def _current_time(self) -> datetime:
        """現在日時をUTCへ正規化する。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
