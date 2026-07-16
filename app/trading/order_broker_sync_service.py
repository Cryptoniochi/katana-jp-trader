"""ローカル注文とBroker側の注文状態を安全に同期する。"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.trading.broker_adapter import (
    BrokerAdapter,
    BrokerOrderSnapshot,
)
from app.trading.order_models import (
    OrderStatus,
    TradeOrderRecord,
)
from app.trading.order_repository import (
    OrderStateTransitionError,
)


class OrderRepositorySynchronizer(Protocol):
    """Broker同期で利用するOrderRepositoryのインターフェース。"""

    def get(
        self,
        order_id: str,
    ) -> TradeOrderRecord:
        """注文IDに一致する注文を返す。"""

    def transition(
        self,
        order_id: str,
        *,
        target_status: OrderStatus,
        filled_quantity: int | None = None,
        average_fill_price: float | None = None,
        broker_order_id: str | None = None,
        status_reason: str | None = None,
        error_message: str | None = None,
    ) -> TradeOrderRecord:
        """注文を許可された次状態へ更新する。"""


class OrderBrokerSyncDecision(StrEnum):
    """Broker同期処理の結果。"""

    SUBMITTED = "submitted"
    SYNCHRONIZED = "synchronized"
    UNCHANGED = "unchanged"
    CANCELLED = "cancelled"
    FAILED = "failed"


class OrderBrokerSyncError(RuntimeError):
    """注文・Broker同期処理の基底例外。"""


class OrderBrokerConsistencyError(OrderBrokerSyncError):
    """ローカル注文とBroker注文の不整合を表す。"""


class OrderBrokerStatusError(OrderBrokerSyncError):
    """Brokerから不正な注文状態が返されたことを表す。"""


@dataclass(frozen=True, slots=True)
class OrderBrokerSyncResult:
    """注文とBroker状態を同期した結果。"""

    decision: OrderBrokerSyncDecision
    order_record: TradeOrderRecord | None
    broker_snapshot: BrokerOrderSnapshot | None
    message: str | None

    @property
    def was_submitted(self) -> bool:
        """Brokerへ新規送信したか返す。"""

        return (
            self.decision
            is OrderBrokerSyncDecision.SUBMITTED
        )

    @property
    def was_synchronized(self) -> bool:
        """Broker状態をローカルへ反映したか返す。"""

        return self.decision in {
            OrderBrokerSyncDecision.SUBMITTED,
            OrderBrokerSyncDecision.SYNCHRONIZED,
            OrderBrokerSyncDecision.CANCELLED,
        }

    @property
    def was_unchanged(self) -> bool:
        """状態変更がなかったか返す。"""

        return (
            self.decision
            is OrderBrokerSyncDecision.UNCHANGED
        )

    @property
    def is_failed(self) -> bool:
        """同期に失敗したか返す。"""

        return (
            self.decision
            is OrderBrokerSyncDecision.FAILED
        )


class OrderBrokerSyncService:
    """OrderRepositoryとBrokerAdapterを同期する。"""

    def __init__(
        self,
        *,
        order_repository: OrderRepositorySynchronizer,
        broker: BrokerAdapter,
    ) -> None:
        """注文RepositoryとBrokerを設定する。"""

        self.order_repository = order_repository
        self.broker = broker

    def submit(
        self,
        order_id: str,
        *,
        continue_on_error: bool = False,
    ) -> OrderBrokerSyncResult:
        """NEW注文をBrokerへ送信し、結果をSQLiteへ反映する。"""

        try:
            local_order = self.order_repository.get(
                order_id,
            )

            if local_order.status is not OrderStatus.NEW:
                return self._submit_existing_order(
                    local_order,
                )

            queued_order = self.order_repository.transition(
                local_order.order_id,
                target_status=OrderStatus.QUEUED,
                status_reason=(
                    "queued for broker submission"
                ),
            )

            try:
                broker_snapshot = self.broker.submit_order(
                    queued_order.order,
                )

            except Exception as error:
                self._mark_failed_after_submission_error(
                    queued_order,
                    error,
                )
                raise

            synchronized_order = self._apply_snapshot(
                local_order=queued_order,
                snapshot=broker_snapshot,
            )

            return OrderBrokerSyncResult(
                decision=(
                    OrderBrokerSyncDecision.SUBMITTED
                ),
                order_record=synchronized_order,
                broker_snapshot=broker_snapshot,
                message=None,
            )

        except Exception as error:
            if not continue_on_error:
                raise

            return OrderBrokerSyncResult(
                decision=OrderBrokerSyncDecision.FAILED,
                order_record=None,
                broker_snapshot=None,
                message=str(error),
            )

    def refresh(
        self,
        order_id: str,
        *,
        continue_on_error: bool = False,
    ) -> OrderBrokerSyncResult:
        """Broker注文を照会し、最新状態をSQLiteへ反映する。"""

        try:
            local_order = self.order_repository.get(
                order_id,
            )

            if local_order.broker_order_id is None:
                raise OrderBrokerConsistencyError(
                    "Broker注文IDがないため照会できません。 "
                    f"order_id={local_order.order_id} "
                    f"status={local_order.status.value}"
                )

            broker_snapshot = self.broker.get_order(
                local_order.broker_order_id,
            )

            self._validate_snapshot_identity(
                local_order=local_order,
                snapshot=broker_snapshot,
            )

            if self._snapshot_matches_local(
                local_order=local_order,
                snapshot=broker_snapshot,
            ):
                return OrderBrokerSyncResult(
                    decision=(
                        OrderBrokerSyncDecision.UNCHANGED
                    ),
                    order_record=local_order,
                    broker_snapshot=broker_snapshot,
                    message=None,
                )

            synchronized_order = self._apply_snapshot(
                local_order=local_order,
                snapshot=broker_snapshot,
            )

            return OrderBrokerSyncResult(
                decision=(
                    OrderBrokerSyncDecision.SYNCHRONIZED
                ),
                order_record=synchronized_order,
                broker_snapshot=broker_snapshot,
                message=None,
            )

        except Exception as error:
            if not continue_on_error:
                raise

            return OrderBrokerSyncResult(
                decision=OrderBrokerSyncDecision.FAILED,
                order_record=None,
                broker_snapshot=None,
                message=str(error),
            )

    def cancel(
        self,
        order_id: str,
        *,
        continue_on_error: bool = False,
    ) -> OrderBrokerSyncResult:
        """Broker注文を取り消し、取消状態をSQLiteへ反映する。"""

        try:
            local_order = self.order_repository.get(
                order_id,
            )

            if local_order.status.is_terminal:
                raise OrderBrokerStatusError(
                    "終了済み注文は取り消せません。 "
                    f"order_id={local_order.order_id} "
                    f"status={local_order.status.value}"
                )

            if local_order.broker_order_id is None:
                if local_order.status in {
                    OrderStatus.NEW,
                    OrderStatus.QUEUED,
                }:
                    cancelled_order = (
                        self.order_repository.transition(
                            local_order.order_id,
                            target_status=(
                                OrderStatus.CANCELLED
                            ),
                            status_reason=(
                                "cancelled before "
                                "broker submission"
                            ),
                        )
                    )

                    return OrderBrokerSyncResult(
                        decision=(
                            OrderBrokerSyncDecision.CANCELLED
                        ),
                        order_record=cancelled_order,
                        broker_snapshot=None,
                        message=None,
                    )

                raise OrderBrokerConsistencyError(
                    "Broker注文IDがないため"
                    "Broker取消を実行できません。 "
                    f"order_id={local_order.order_id} "
                    f"status={local_order.status.value}"
                )

            broker_snapshot = self.broker.cancel_order(
                local_order.broker_order_id,
            )

            self._validate_snapshot_identity(
                local_order=local_order,
                snapshot=broker_snapshot,
            )

            if (
                broker_snapshot.status
                is not OrderStatus.CANCELLED
            ):
                raise OrderBrokerStatusError(
                    "Broker取消結果がCANCELLEDでは"
                    "ありません。 "
                    f"order_id={local_order.order_id} "
                    f"broker_status="
                    f"{broker_snapshot.status.value}"
                )

            synchronized_order = self._apply_snapshot(
                local_order=local_order,
                snapshot=broker_snapshot,
            )

            return OrderBrokerSyncResult(
                decision=(
                    OrderBrokerSyncDecision.CANCELLED
                ),
                order_record=synchronized_order,
                broker_snapshot=broker_snapshot,
                message=None,
            )

        except Exception as error:
            if not continue_on_error:
                raise

            return OrderBrokerSyncResult(
                decision=OrderBrokerSyncDecision.FAILED,
                order_record=None,
                broker_snapshot=None,
                message=str(error),
            )

    def _submit_existing_order(
        self,
        local_order: TradeOrderRecord,
    ) -> OrderBrokerSyncResult:
        """送信済みまたは終了済み注文を冪等に扱う。"""

        if local_order.broker_order_id is not None:
            return self.refresh(
                local_order.order_id,
            )

        if local_order.status is OrderStatus.QUEUED:
            broker_snapshot = self.broker.submit_order(
                local_order.order,
            )

            synchronized_order = self._apply_snapshot(
                local_order=local_order,
                snapshot=broker_snapshot,
            )

            return OrderBrokerSyncResult(
                decision=(
                    OrderBrokerSyncDecision.SUBMITTED
                ),
                order_record=synchronized_order,
                broker_snapshot=broker_snapshot,
                message=(
                    "QUEUED状態からBroker送信を"
                    "再開しました。"
                ),
            )

        raise OrderBrokerStatusError(
            "Broker注文IDのない注文を送信できません。 "
            f"order_id={local_order.order_id} "
            f"status={local_order.status.value}"
        )

    def _apply_snapshot(
        self,
        *,
        local_order: TradeOrderRecord,
        snapshot: BrokerOrderSnapshot,
    ) -> TradeOrderRecord:
        """Broker Snapshotを許可された状態遷移で反映する。"""

        self._validate_snapshot_identity(
            local_order=local_order,
            snapshot=snapshot,
        )

        current = local_order

        if current.status is OrderStatus.QUEUED:
            current = self.order_repository.transition(
                current.order_id,
                target_status=OrderStatus.SENT,
                broker_order_id=(
                    snapshot.broker_order_id
                ),
                status_reason=(
                    snapshot.status_reason
                    or "broker accepted order"
                ),
            )

        elif (
            current.status is OrderStatus.NEW
            and snapshot.status
            is not OrderStatus.NEW
        ):
            current = self.order_repository.transition(
                current.order_id,
                target_status=OrderStatus.QUEUED,
                status_reason=(
                    "queued during broker reconciliation"
                ),
            )

            current = self.order_repository.transition(
                current.order_id,
                target_status=OrderStatus.SENT,
                broker_order_id=(
                    snapshot.broker_order_id
                ),
                status_reason=(
                    snapshot.status_reason
                    or "broker accepted order"
                ),
            )

        elif (
            current.broker_order_id is None
            and snapshot.status
            in {
                OrderStatus.SENT,
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.FILLED,
                OrderStatus.CANCELLED,
                OrderStatus.REJECTED,
                OrderStatus.FAILED,
            }
        ):
            raise OrderBrokerConsistencyError(
                "Broker注文IDを保存できない"
                "ローカル状態です。 "
                f"order_id={current.order_id} "
                f"status={current.status.value}"
            )

        if snapshot.status is OrderStatus.SENT:
            return current

        if (
            snapshot.status
            is OrderStatus.PARTIALLY_FILLED
        ):
            return self.order_repository.transition(
                current.order_id,
                target_status=(
                    OrderStatus.PARTIALLY_FILLED
                ),
                filled_quantity=(
                    snapshot.filled_quantity
                ),
                average_fill_price=(
                    snapshot.average_fill_price
                ),
                broker_order_id=(
                    snapshot.broker_order_id
                ),
                status_reason=(
                    snapshot.status_reason
                ),
            )

        if snapshot.status is OrderStatus.FILLED:
            return self.order_repository.transition(
                current.order_id,
                target_status=OrderStatus.FILLED,
                filled_quantity=(
                    snapshot.filled_quantity
                ),
                average_fill_price=(
                    snapshot.average_fill_price
                ),
                broker_order_id=(
                    snapshot.broker_order_id
                ),
                status_reason=(
                    snapshot.status_reason
                ),
            )

        if snapshot.status is OrderStatus.CANCELLED:
            return self.order_repository.transition(
                current.order_id,
                target_status=OrderStatus.CANCELLED,
                filled_quantity=(
                    snapshot.filled_quantity
                ),
                average_fill_price=(
                    snapshot.average_fill_price
                ),
                broker_order_id=(
                    snapshot.broker_order_id
                ),
                status_reason=(
                    snapshot.status_reason
                ),
            )

        if snapshot.status is OrderStatus.REJECTED:
            return self.order_repository.transition(
                current.order_id,
                target_status=OrderStatus.REJECTED,
                filled_quantity=(
                    snapshot.filled_quantity
                ),
                average_fill_price=(
                    snapshot.average_fill_price
                ),
                broker_order_id=(
                    snapshot.broker_order_id
                ),
                status_reason=(
                    snapshot.status_reason
                ),
                error_message=(
                    snapshot.status_reason
                    or "broker rejected order"
                ),
            )

        if snapshot.status is OrderStatus.FAILED:
            return self.order_repository.transition(
                current.order_id,
                target_status=OrderStatus.FAILED,
                filled_quantity=(
                    snapshot.filled_quantity
                ),
                average_fill_price=(
                    snapshot.average_fill_price
                ),
                broker_order_id=(
                    snapshot.broker_order_id
                ),
                status_reason=(
                    snapshot.status_reason
                ),
                error_message=(
                    snapshot.status_reason
                    or "broker order failed"
                ),
            )

        if snapshot.status in {
            OrderStatus.NEW,
            OrderStatus.QUEUED,
        }:
            raise OrderBrokerStatusError(
                "Brokerからローカル専用状態が"
                "返されました。 "
                f"broker_status="
                f"{snapshot.status.value}"
            )

        raise OrderBrokerStatusError(
            "未対応のBroker注文状態です。 "
            f"broker_status={snapshot.status.value}"
        )

    def _mark_failed_after_submission_error(
        self,
        queued_order: TradeOrderRecord,
        error: Exception,
    ) -> None:
        """Broker送信例外をローカルFAILED状態へ保存する。"""

        try:
            self.order_repository.transition(
                queued_order.order_id,
                target_status=OrderStatus.FAILED,
                status_reason="broker submission failed",
                error_message=str(error),
            )

        except (
            OrderStateTransitionError,
            Exception,
        ):
            # 元のBroker例外を優先して再送出するため、
            # FAILED保存の二次例外はここでは握りつぶす。
            return

    @staticmethod
    def _validate_snapshot_identity(
        *,
        local_order: TradeOrderRecord,
        snapshot: BrokerOrderSnapshot,
    ) -> None:
        """Broker Snapshotがローカル注文と一致するか検証する。"""

        if (
            snapshot.client_order_id
            != local_order.order_id
        ):
            raise OrderBrokerConsistencyError(
                "Brokerのクライアント注文IDが"
                "ローカル注文と一致しません。 "
                f"local={local_order.order_id} "
                f"broker={snapshot.client_order_id}"
            )

        if snapshot.code != local_order.code:
            raise OrderBrokerConsistencyError(
                "Brokerの銘柄コードが"
                "ローカル注文と一致しません。 "
                f"local={local_order.code} "
                f"broker={snapshot.code}"
            )

        if snapshot.side is not local_order.order.side:
            raise OrderBrokerConsistencyError(
                "Brokerの売買方向が"
                "ローカル注文と一致しません。 "
                f"local={local_order.order.side.value} "
                f"broker={snapshot.side.value}"
            )

        if (
            snapshot.quantity
            != local_order.order.quantity
        ):
            raise OrderBrokerConsistencyError(
                "Brokerの注文数量が"
                "ローカル注文と一致しません。 "
                f"local={local_order.order.quantity} "
                f"broker={snapshot.quantity}"
            )

        if (
            local_order.broker_order_id is not None
            and local_order.broker_order_id
            != snapshot.broker_order_id
        ):
            raise OrderBrokerConsistencyError(
                "Broker注文IDが保存済み注文と"
                "一致しません。 "
                f"local={local_order.broker_order_id} "
                f"broker={snapshot.broker_order_id}"
            )

    @staticmethod
    def _snapshot_matches_local(
        *,
        local_order: TradeOrderRecord,
        snapshot: BrokerOrderSnapshot,
    ) -> bool:
        """Broker状態がローカル状態と一致するか返す。"""

        return (
            local_order.status is snapshot.status
            and local_order.filled_quantity
            == snapshot.filled_quantity
            and local_order.average_fill_price
            == snapshot.average_fill_price
            and local_order.broker_order_id
            == snapshot.broker_order_id
            and local_order.status_reason
            == snapshot.status_reason
        )