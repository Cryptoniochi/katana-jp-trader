"""BacktestOrderQueueとServiceの統合テスト。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.backtest.order_queue import (
    BacktestOrderQueue,
    DuplicateQueuedOrderError,
    QueuedBacktestOrder,
)
from app.backtest.order_queue_service import (
    BacktestOrderQueueDecision,
    BacktestOrderQueueService,
)
from app.database import initialize_database
from app.trading.order_models import (
    OrderSide,
    OrderStatus,
    OrderType,
    TradeOrder,
    TradeOrderRecord,
)
from app.trading.order_repository import OrderRepository
from app.trading.order_service import SignalOrderService
from app.trading.signal_models import (
    SignalAction,
    SignalStatus,
    TradeSignal,
)
from app.trading.signal_repository import SignalRepository


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
    generated_at: datetime = CURRENT_TIME,
) -> TradeSignal:
    """標準的なバックテスト用シグナルを作成する。"""

    return TradeSignal(
        signal_id=signal_id,
        code="7203",
        strategy_name="test-strategy",
        action=SignalAction.BUY,
        generated_at=generated_at,
        signal_price=2500.0,
        quantity=100,
        reason="backtest queue test",
    )


def create_environment(
    tmp_path: Path,
) -> tuple[
    SignalRepository,
    OrderRepository,
    BacktestOrderQueue,
    BacktestOrderQueueService,
]:
    """実SQLiteを使う注文キュー環境を作成する。"""

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
    order_service = SignalOrderService(
        signal_repository=signal_repository,
        order_repository=order_repository,
    )
    queue = BacktestOrderQueue()
    service = BacktestOrderQueueService(
        signal_repository=signal_repository,
        order_service=order_service,
        order_queue=queue,
        now_provider=lambda: CURRENT_TIME,
    )

    return (
        signal_repository,
        order_repository,
        queue,
        service,
    )


def test_queue_is_fifo() -> None:
    """注文を登録順に取り出す。"""

    queue = BacktestOrderQueue()

    def make_item(index: int) -> QueuedBacktestOrder:
        order = TradeOrder(
            order_id=f"order-{index}",
            signal_id=f"signal-{index}",
            code="7203",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
        )
        record = TradeOrderRecord(
            id=index,
            order=order,
            status=OrderStatus.NEW,
            filled_quantity=0,
            average_fill_price=None,
            broker_order_id=None,
            status_reason=None,
            error_message=None,
            created_at=CURRENT_TIME,
            updated_at=CURRENT_TIME,
            submitted_at=None,
            completed_at=None,
        )
        return QueuedBacktestOrder(
            order_record=record,
            enqueued_at=CURRENT_TIME,
        )

    first = make_item(1)
    second = make_item(2)

    queue.enqueue(first)
    queue.enqueue(second)

    assert queue.count == 2
    assert queue.peek() == first
    assert queue.pop() == first
    assert queue.pop() == second
    assert queue.pop() is None
    assert queue.is_empty


def test_queue_rejects_duplicate_order() -> None:
    """同じ注文IDの重複登録を拒否する。"""

    queue = BacktestOrderQueue()
    order = TradeOrder(
        order_id="order-1",
        signal_id="signal-1",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=100,
    )
    record = TradeOrderRecord(
        id=1,
        order=order,
        status=OrderStatus.NEW,
        filled_quantity=0,
        average_fill_price=None,
        broker_order_id=None,
        status_reason=None,
        error_message=None,
        created_at=CURRENT_TIME,
        updated_at=CURRENT_TIME,
        submitted_at=None,
        completed_at=None,
    )
    item = QueuedBacktestOrder(
        order_record=record,
        enqueued_at=CURRENT_TIME,
    )

    queue.enqueue(item)

    with pytest.raises(
        DuplicateQueuedOrderError,
        match="注文ID",
    ):
        queue.enqueue(item)


def test_service_saves_signal_creates_order_and_enqueues(
    tmp_path: Path,
) -> None:
    """シグナル保存から注文キュー登録まで実行する。"""

    (
        signal_repository,
        order_repository,
        queue,
        service,
    ) = create_environment(tmp_path)

    result = service.enqueue_signal(
        create_signal()
    )

    assert result.decision is (
        BacktestOrderQueueDecision.ENQUEUED
    )
    assert result.was_enqueued
    assert not result.was_existing
    assert not result.is_failed
    assert result.order_record is not None
    assert result.queued_order is not None

    assert signal_repository.count(
        status=SignalStatus.PROCESSED
    ) == 1
    assert order_repository.count(
        status=OrderStatus.NEW
    ) == 1
    assert queue.count == 1
    assert queue.peek() == result.queued_order


def test_service_is_idempotent_for_same_signal(
    tmp_path: Path,
) -> None:
    """同じシグナルを再実行してもキューを重複させない。"""

    (
        signal_repository,
        order_repository,
        queue,
        service,
    ) = create_environment(tmp_path)

    signal = create_signal()

    first = service.enqueue_signal(signal)
    second = service.enqueue_signal(signal)

    assert first.was_enqueued
    assert second.was_existing
    assert queue.count == 1
    assert order_repository.count() == 1
    assert signal_repository.count() == 1


def test_service_enqueues_multiple_signals_in_order(
    tmp_path: Path,
) -> None:
    """複数シグナルを入力順でキューへ登録する。"""

    (
        _signal_repository,
        _order_repository,
        queue,
        service,
    ) = create_environment(tmp_path)

    signals = (
        create_signal(
            signal_id="signal-001",
            generated_at=CURRENT_TIME,
        ),
        create_signal(
            signal_id="signal-002",
            generated_at=(
                CURRENT_TIME + timedelta(minutes=5)
            ),
        ),
    )

    results = service.enqueue_signals(signals)

    assert all(
        result.was_enqueued
        for result in results
    )
    assert [
        item.signal_id
        for item in queue.snapshot()
    ] == [
        "signal-001",
        "signal-002",
    ]


def test_service_creates_limit_order(
    tmp_path: Path,
) -> None:
    """指値条件を既存OrderServiceへ渡す。"""

    (
        _signal_repository,
        _order_repository,
        _queue,
        service,
    ) = create_environment(tmp_path)

    result = service.enqueue_signal(
        create_signal(),
        order_type=OrderType.LIMIT,
        limit_price=2490.0,
    )

    assert result.order_record is not None
    assert result.order_record.order.order_type is (
        OrderType.LIMIT
    )
    assert result.order_record.order.limit_price == pytest.approx(
        2490.0
    )


def test_service_records_failure_when_enabled(
    tmp_path: Path,
) -> None:
    """継続設定時は注文検証エラーを失敗結果へ変換する。"""

    (
        _signal_repository,
        _order_repository,
        queue,
        service,
    ) = create_environment(tmp_path)

    result = service.enqueue_signal(
        create_signal(),
        order_type=OrderType.LIMIT,
        continue_on_error=True,
    )

    assert result.decision is (
        BacktestOrderQueueDecision.FAILED
    )
    assert result.is_failed
    assert result.order_record is None
    assert result.queued_order is None
    assert "指値価格" in (result.message or "")
    assert queue.count == 0


def test_queue_rejects_naive_enqueued_at() -> None:
    """タイムゾーンなし登録日時を拒否する。"""

    order = TradeOrder(
        order_id="order-1",
        signal_id="signal-1",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=100,
    )
    record = TradeOrderRecord(
        id=1,
        order=order,
        status=OrderStatus.NEW,
        filled_quantity=0,
        average_fill_price=None,
        broker_order_id=None,
        status_reason=None,
        error_message=None,
        created_at=CURRENT_TIME,
        updated_at=CURRENT_TIME,
        submitted_at=None,
        completed_at=None,
    )

    with pytest.raises(ValueError, match="タイムゾーン"):
        QueuedBacktestOrder(
            order_record=record,
            enqueued_at=datetime(
                2026,
                7,
                1,
                9,
                30,
            ),
        )
