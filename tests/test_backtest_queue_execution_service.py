"""BacktestQueueExecutionServiceの統合テスト。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.backtest.order_queue import BacktestOrderQueue
from app.backtest.order_queue_service import (
    BacktestOrderQueueService,
)
from app.backtest.queue_execution_service import (
    BacktestQueueExecutionDecision,
    BacktestQueueExecutionService,
)
from app.database import initialize_database
from app.trading.order_broker_sync_service import (
    OrderBrokerSyncService,
)
from app.trading.order_models import (
    OrderStatus,
    OrderType,
)
from app.trading.order_repository import OrderRepository
from app.trading.order_service import SignalOrderService
from app.trading.paper_broker import (
    PaperBroker,
    PaperBrokerSettings,
)
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)
from app.trading.signal_repository import SignalRepository
from app.trading.trade_execution_repository import (
    TradeExecutionRepository,
)


CURRENT_TIME = datetime(
    2026,
    7,
    1,
    0,
    30,
    tzinfo=timezone.utc,
)


def create_signal(
    *,
    signal_id: str = "signal-001",
    code: str = "7203",
    quantity: int = 100,
    generated_at: datetime = CURRENT_TIME,
) -> TradeSignal:
    """標準的なバックテスト用BUYシグナルを作成する。"""

    return TradeSignal(
        signal_id=signal_id,
        code=code,
        strategy_name="test-strategy",
        action=SignalAction.BUY,
        generated_at=generated_at,
        signal_price=2500.0,
        quantity=quantity,
        reason="queue execution test",
    )


def create_environment(
    tmp_path: Path,
    *,
    initial_cash: float = 1_000_000.0,
    market_price: float = 2500.0,
) -> tuple[
    BacktestOrderQueue,
    BacktestOrderQueueService,
    BacktestQueueExecutionService,
    OrderRepository,
    TradeExecutionRepository,
    PaperBroker,
]:
    """実SQLiteとPaperBrokerを使う統合環境を作成する。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    signal_repository = SignalRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    )
    order_repository = OrderRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    )
    execution_repository = TradeExecutionRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    )

    order_service = SignalOrderService(
        signal_repository=signal_repository,
        order_repository=order_repository,
    )

    queue = BacktestOrderQueue()

    queue_service = BacktestOrderQueueService(
        signal_repository=signal_repository,
        order_service=order_service,
        order_queue=queue,
        now_provider=lambda: CURRENT_TIME,
    )

    broker = PaperBroker(
        price_provider=lambda _code: market_price,
        settings=PaperBrokerSettings(
            initial_cash=initial_cash,
        ),
        now_provider=lambda: CURRENT_TIME,
    )

    sync_service = OrderBrokerSyncService(
        order_repository=order_repository,
        broker=broker,
    )

    execution_service = BacktestQueueExecutionService(
        order_queue=queue,
        broker_sync_service=sync_service,
        execution_repository=execution_repository,
        broker_name=broker.broker_name,
    )

    return (
        queue,
        queue_service,
        execution_service,
        order_repository,
        execution_repository,
        broker,
    )


def test_service_executes_market_order_and_saves_fill(
    tmp_path: Path,
) -> None:
    """キュー注文を全約定し約定台帳へ保存する。"""

    (
        queue,
        queue_service,
        service,
        order_repository,
        execution_repository,
        broker,
    ) = create_environment(tmp_path)

    queued = queue_service.enqueue_signal(
        create_signal()
    )

    result = service.execute_next()

    assert queued.queued_order is not None
    assert result is not None
    assert result.decision is (
        BacktestQueueExecutionDecision.TERMINAL
    )
    assert result.is_terminal
    assert result.execution_record is not None
    assert result.execution_record.execution.quantity == 100
    assert (
        result.execution_record.execution.execution_price
        == pytest.approx(2500.0)
    )

    assert queue.is_empty
    assert order_repository.count(
        status=OrderStatus.FILLED
    ) == 1
    assert execution_repository.count() == 1
    assert broker.list_positions()[0].quantity == 100


def test_service_submits_active_limit_order_without_fill(
    tmp_path: Path,
) -> None:
    """条件未到達の指値注文をACTIVEとして返す。"""

    (
        queue,
        queue_service,
        service,
        order_repository,
        execution_repository,
        broker,
    ) = create_environment(
        tmp_path,
        market_price=2500.0,
    )

    queue_service.enqueue_signal(
        create_signal(),
        order_type=OrderType.LIMIT,
        limit_price=2400.0,
    )

    result = service.execute_next()

    assert result is not None
    assert result.decision is (
        BacktestQueueExecutionDecision.ACTIVE
    )
    assert result.is_active
    assert result.execution_record is None
    assert queue.is_empty
    assert order_repository.count(
        status=OrderStatus.SENT
    ) == 1
    assert execution_repository.count() == 0
    assert broker.list_positions() == []


def test_service_executes_orders_fifo(
    tmp_path: Path,
) -> None:
    """複数注文をFIFO順で執行する。"""

    (
        queue,
        queue_service,
        service,
        _order_repository,
        execution_repository,
        broker,
    ) = create_environment(
        tmp_path,
        initial_cash=2_000_000.0,
    )

    queue_service.enqueue_signals(
        (
            create_signal(
                signal_id="signal-001",
                code="7203",
            ),
            create_signal(
                signal_id="signal-002",
                code="8306",
                generated_at=(
                    CURRENT_TIME
                    + timedelta(minutes=5)
                ),
            ),
        )
    )

    result = service.execute_all()

    assert result.processed_count == 2
    assert result.terminal_count == 2
    assert result.active_count == 0
    assert result.failed_count == 0
    assert result.saved_execution_count == 2
    assert result.is_successful
    assert [
        item.queued_order.signal_id
        for item in result.items
    ] == [
        "signal-001",
        "signal-002",
    ]
    assert queue.is_empty
    assert execution_repository.count() == 2
    assert len(broker.list_positions()) == 2


def test_service_respects_limit(
    tmp_path: Path,
) -> None:
    """指定件数だけキュー注文を処理する。"""

    (
        queue,
        queue_service,
        service,
        _order_repository,
        execution_repository,
        _broker,
    ) = create_environment(
        tmp_path,
        initial_cash=2_000_000.0,
    )

    queue_service.enqueue_signals(
        (
            create_signal(
                signal_id="signal-001",
                code="7203",
            ),
            create_signal(
                signal_id="signal-002",
                code="8306",
            ),
        )
    )

    result = service.execute_all(limit=1)

    assert result.processed_count == 1
    assert queue.count == 1
    assert execution_repository.count() == 1


def test_service_records_failure_and_continues(
    tmp_path: Path,
) -> None:
    """買付余力不足を失敗結果にして後続注文を処理する。"""

    (
        queue,
        queue_service,
        service,
        order_repository,
        execution_repository,
        broker,
    ) = create_environment(
        tmp_path,
        initial_cash=300_000.0,
    )

    queue_service.enqueue_signals(
        (
            create_signal(
                signal_id="signal-large",
                code="7203",
                quantity=200,
            ),
            create_signal(
                signal_id="signal-small",
                code="8306",
                quantity=100,
            ),
        )
    )

    result = service.execute_all(
        continue_on_error=True
    )

    assert result.processed_count == 2
    assert result.failed_count == 1
    assert result.terminal_count == 1
    assert result.saved_execution_count == 1
    assert not result.is_successful
    assert "買付余力" in (
        result.items[0].message or ""
    )
    assert queue.is_empty
    assert order_repository.count(
        status=OrderStatus.FAILED
    ) == 1
    assert order_repository.count(
        status=OrderStatus.FILLED
    ) == 1
    assert execution_repository.count() == 1
    assert len(broker.list_positions()) == 1


def test_service_keeps_order_when_error_is_raised(
    tmp_path: Path,
) -> None:
    """継続無効時は例外を再送出しキュー先頭を保持する。"""

    (
        queue,
        queue_service,
        service,
        _order_repository,
        _execution_repository,
        _broker,
    ) = create_environment(
        tmp_path,
        initial_cash=100_000.0,
    )

    queue_service.enqueue_signal(
        create_signal()
    )

    with pytest.raises(
        Exception,
        match="買付余力",
    ):
        service.execute_next(
            continue_on_error=False
        )

    assert queue.count == 1


def test_service_returns_none_for_empty_queue(
    tmp_path: Path,
) -> None:
    """空キューではNoneを返す。"""

    (
        _queue,
        _queue_service,
        service,
        _order_repository,
        _execution_repository,
        _broker,
    ) = create_environment(tmp_path)

    assert service.execute_next() is None
    assert service.execute_all().items == ()


def test_service_rejects_invalid_settings(
    tmp_path: Path,
) -> None:
    """不正なBroker名・約定コスト・処理件数を拒否する。"""

    (
        queue,
        _queue_service,
        service,
        _order_repository,
        execution_repository,
        _broker,
    ) = create_environment(tmp_path)

    with pytest.raises(ValueError, match="Broker名"):
        BacktestQueueExecutionService(
            order_queue=queue,
            broker_sync_service=service.broker_sync_service,
            execution_repository=execution_repository,
            broker_name=" ",
        )

    with pytest.raises(ValueError, match="約定手数料"):
        BacktestQueueExecutionService(
            order_queue=queue,
            broker_sync_service=service.broker_sync_service,
            execution_repository=execution_repository,
            broker_name="paper",
            commission_per_execution=-1.0,
        )

    with pytest.raises(ValueError, match="処理件数"):
        service.execute_all(limit=0)
