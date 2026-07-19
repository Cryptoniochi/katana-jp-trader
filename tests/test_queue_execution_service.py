"""BacktestQueueExecutionServiceの約定Observerテスト。"""

from datetime import datetime, timezone

import pytest

from app.backtest.queue_execution_service import (
    BacktestQueueExecutionService,
)
from app.trading.order_models import OrderSide
from app.trading.trade_execution_models import (
    TradeExecution,
    TradeExecutionRecord,
)


NOW = datetime(
    2026,
    7,
    21,
    0,
    15,
    tzinfo=timezone.utc,
)


class FakeObserver:
    def __init__(
        self,
        *,
        error: Exception | None = None,
    ) -> None:
        self.error = error
        self.records = []

    def record(self, execution_record) -> None:
        self.records.append(execution_record)

        if self.error is not None:
            raise self.error


def execution_record() -> TradeExecutionRecord:
    execution = TradeExecution(
        execution_id="broker-1:100",
        signal_id="signal-1",
        order_id="order-1",
        broker_order_id="broker-1",
        code="7203",
        side=OrderSide.BUY,
        quantity=100,
        execution_price=2965.0,
        executed_at=NOW,
        broker_name="paper",
    )

    return TradeExecutionRecord(
        id=1,
        execution=execution,
        created_at=NOW,
        updated_at=NOW,
    )


def create_service(
    *,
    observers=(),
    continue_on_notification_error=True,
):
    return BacktestQueueExecutionService(
        order_queue=object(),
        broker_sync_service=object(),
        execution_repository=object(),
        broker_name="paper",
        execution_observers=observers,
        continue_on_notification_error=(
            continue_on_notification_error
        ),
    )


def test_new_execution_is_sent_to_observers() -> None:
    observer = FakeObserver()
    service = create_service(
        observers=(observer,)
    )
    record = execution_record()

    service._notify_execution_observers(
        record
    )

    assert observer.records == [record]


def test_observer_error_is_isolated_by_default() -> None:
    observer = FakeObserver(
        error=RuntimeError(
            "notification unavailable"
        )
    )
    service = create_service(
        observers=(observer,)
    )

    service._notify_execution_observers(
        execution_record()
    )

    assert len(observer.records) == 1


def test_observer_error_can_be_fail_fast() -> None:
    observer = FakeObserver(
        error=RuntimeError(
            "notification unavailable"
        )
    )
    service = create_service(
        observers=(observer,),
        continue_on_notification_error=False,
    )

    with pytest.raises(
        RuntimeError,
        match="notification unavailable",
    ):
        service._notify_execution_observers(
            execution_record()
        )
