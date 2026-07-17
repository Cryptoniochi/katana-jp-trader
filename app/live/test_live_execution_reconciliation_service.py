"""LiveExecutionReconciliationServiceのテスト。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.live.live_execution_reconciliation_service import (
    LiveExecutionReconciliationDecision,
    LiveExecutionReconciliationService,
)
from app.trading.broker_adapter import (
    BrokerOrderSnapshot,
)
from app.trading.order_broker_sync_service import (
    OrderBrokerSyncDecision,
    OrderBrokerSyncResult,
)
from app.trading.order_models import (
    OrderSide,
    OrderStatus,
    OrderType,
    TradeOrder,
    TradeOrderRecord,
)
from app.trading.trade_execution_models import (
    TradeExecution,
    TradeExecutionRecord,
)


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def order_record(
    *,
    status: OrderStatus,
    filled_quantity: int,
    average_fill_price: float | None,
) -> TradeOrderRecord:
    """保存済み注文を作成する。"""

    terminal = status.is_terminal

    return TradeOrderRecord(
        id=1,
        order=TradeOrder(
            order_id="order-001",
            signal_id="signal-001",
            code="7203",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
        ),
        status=status,
        filled_quantity=filled_quantity,
        average_fill_price=average_fill_price,
        broker_order_id="broker-001",
        status_reason=None,
        error_message=None,
        created_at=NOW,
        updated_at=NOW,
        submitted_at=NOW,
        completed_at=NOW if terminal else None,
    )


def snapshot(
    *,
    status: OrderStatus,
    filled_quantity: int,
    average_fill_price: float | None,
) -> BrokerOrderSnapshot:
    """Broker注文Snapshotを作成する。"""

    return BrokerOrderSnapshot(
        broker_order_id="broker-001",
        client_order_id="order-001",
        code="7203",
        side=OrderSide.BUY,
        status=status,
        quantity=100,
        filled_quantity=filled_quantity,
        average_fill_price=average_fill_price,
        submitted_at=NOW,
        updated_at=NOW,
    )


class FakeSyncService:
    """固定Broker同期結果を返す。"""

    def __init__(
        self,
        result: OrderBrokerSyncResult,
    ) -> None:
        self.result = result
        self.requested: list[str] = []
        self.fail = False

    def refresh(
        self,
        order_id: str,
        *,
        continue_on_error: bool = False,
    ) -> OrderBrokerSyncResult:
        self.requested.append(order_id)

        if self.fail:
            raise RuntimeError("refresh failed")

        return self.result


class FakeExecutionRepository:
    """インメモリ約定台帳。"""

    def __init__(
        self,
        records: list[TradeExecutionRecord] | None = None,
    ) -> None:
        self.records = list(records or [])
        self.saved: list[TradeExecution] = []

    def find_by_order(
        self,
        order_id: str,
    ) -> list[TradeExecutionRecord]:
        return [
            record
            for record in self.records
            if record.execution.order_id == order_id
        ]

    def save(
        self,
        execution: TradeExecution,
    ) -> TradeExecutionRecord:
        self.saved.append(execution)
        record = TradeExecutionRecord(
            id=len(self.records) + 1,
            execution=execution,
            created_at=NOW,
            updated_at=NOW,
        )
        self.records.append(record)
        return record


def existing_execution(
    quantity: int,
) -> TradeExecutionRecord:
    """既存約定履歴を作成する。"""

    return TradeExecutionRecord(
        id=1,
        execution=TradeExecution(
            execution_id=f"existing-{quantity}",
            signal_id="signal-001",
            order_id="order-001",
            broker_order_id="broker-001",
            code="7203",
            side=OrderSide.BUY,
            quantity=quantity,
            execution_price=2500.0,
            executed_at=NOW,
            broker_name="paper",
        ),
        created_at=NOW,
        updated_at=NOW,
    )


def create_service(
    *,
    filled_quantity: int,
    status: OrderStatus,
    average_fill_price: float | None,
    records: list[TradeExecutionRecord] | None = None,
):
    """テスト対象とFakeを作成する。"""

    sync = FakeSyncService(
        OrderBrokerSyncResult(
            decision=OrderBrokerSyncDecision.SYNCHRONIZED,
            order_record=order_record(
                status=status,
                filled_quantity=filled_quantity,
                average_fill_price=average_fill_price,
            ),
            broker_snapshot=snapshot(
                status=status,
                filled_quantity=filled_quantity,
                average_fill_price=average_fill_price,
            ),
            message=None,
        )
    )
    repository = FakeExecutionRepository(records)
    service = LiveExecutionReconciliationService(
        broker_sync_service=sync,
        execution_repository=repository,
        broker_name="paper",
        commission_per_execution=10.0,
        slippage_per_execution=2.0,
    )
    return service, sync, repository


def test_saves_first_partial_fill() -> None:
    """最初の部分約定を全数量保存する。"""

    service, _sync, repository = create_service(
        filled_quantity=40,
        status=OrderStatus.PARTIALLY_FILLED,
        average_fill_price=2500.0,
    )

    result = service.reconcile("order-001")

    assert result.was_saved
    assert result.new_filled_quantity == 40
    assert repository.saved[0].quantity == 40
    assert repository.saved[0].execution_id == (
        "broker-001:40"
    )
    assert repository.saved[0].commission == 10.0
    assert repository.saved[0].slippage == 2.0


def test_saves_only_incremental_fill() -> None:
    """累積約定数量から保存済み数量を差し引く。"""

    service, _sync, repository = create_service(
        filled_quantity=100,
        status=OrderStatus.FILLED,
        average_fill_price=2520.0,
        records=[existing_execution(40)],
    )

    result = service.reconcile("order-001")

    assert result.new_filled_quantity == 60
    assert repository.saved[0].quantity == 60
    assert repository.saved[0].execution_id == (
        "broker-001:100"
    )


def test_returns_unchanged_when_already_recorded() -> None:
    """累積約定数量が保存済み数量と同じなら保存しない。"""

    service, _sync, repository = create_service(
        filled_quantity=40,
        status=OrderStatus.PARTIALLY_FILLED,
        average_fill_price=2500.0,
        records=[existing_execution(40)],
    )

    result = service.reconcile("order-001")

    assert result.decision is (
        LiveExecutionReconciliationDecision.UNCHANGED
    )
    assert result.new_filled_quantity == 0
    assert repository.saved == []


def test_rejects_recorded_quantity_above_broker() -> None:
    """ローカル数量がBroker累積数量を超える不整合を検出する。"""

    service, _sync, _repository = create_service(
        filled_quantity=40,
        status=OrderStatus.PARTIALLY_FILLED,
        average_fill_price=2500.0,
        records=[existing_execution(60)],
    )

    with pytest.raises(
        RuntimeError,
        match="上回っています",
    ):
        service.reconcile("order-001")


def test_continue_on_error_returns_failed_result() -> None:
    """継続モードでは再照会例外を失敗結果へ変換する。"""

    service, sync, _repository = create_service(
        filled_quantity=0,
        status=OrderStatus.SENT,
        average_fill_price=None,
    )
    sync.fail = True

    result = service.reconcile(
        "order-001",
        continue_on_error=True,
    )

    assert result.is_failed
    assert result.message == "refresh failed"


def test_reconcile_many_aggregates_results() -> None:
    """一括照合の保存件数と数量を集計する。"""

    service, _sync, _repository = create_service(
        filled_quantity=100,
        status=OrderStatus.FILLED,
        average_fill_price=2500.0,
    )

    result = service.reconcile_many(
        ("order-001",),
    )

    assert result.order_count == 1
    assert result.saved_count == 1
    assert result.failed_count == 0
    assert result.new_filled_quantity == 100
