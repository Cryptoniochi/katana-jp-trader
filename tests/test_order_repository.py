"""売買注文モデルとRepositoryのテスト。"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.database import (
    SCHEMA_VERSION,
    initialize_database,
)
from app.trading.order_models import (
    OrderSide,
    OrderStatus,
    OrderType,
    TradeOrder,
)
from app.trading.order_repository import (
    DuplicateOrderError,
    OrderNotFoundError,
    OrderRepository,
    OrderStateTransitionError,
)
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)
from app.trading.signal_repository import (
    SignalRepository,
)


CREATED_AT = datetime(
    2026,
    7,
    16,
    0,
    20,
    tzinfo=timezone.utc,
)

QUEUED_AT = CREATED_AT + timedelta(
    seconds=1
)

SENT_AT = CREATED_AT + timedelta(
    seconds=2
)

PARTIAL_AT = CREATED_AT + timedelta(
    seconds=3
)

FILLED_AT = CREATED_AT + timedelta(
    seconds=4
)


class SequentialClock:
    """指定日時を順番に返す時計。"""

    def __init__(
        self,
        times: list[datetime],
    ) -> None:
        """返却日時を設定する。"""

        self.times = iter(times)

    def now(self) -> datetime:
        """次の日時を返す。"""

        return next(self.times)


def create_signal() -> TradeSignal:
    """注文元となる売買シグナルを作成する。"""

    return TradeSignal(
        signal_id="signal-001",
        code="7203",
        strategy_name="orb",
        action=SignalAction.BUY,
        generated_at=CREATED_AT,
        signal_price=2500.0,
        quantity=100,
        reason="opening_range_breakout",
    )


def create_order(
    *,
    order_id: str = "order-001",
    signal_id: str = "signal-001",
    code: str = "7203",
    side: OrderSide = OrderSide.BUY,
    order_type: OrderType = OrderType.MARKET,
    quantity: int = 100,
    limit_price: float | None = None,
    stop_price: float | None = None,
) -> TradeOrder:
    """標準的な注文を作成する。"""

    return TradeOrder(
        order_id=order_id,
        signal_id=signal_id,
        code=code,
        side=side,
        order_type=order_type,
        quantity=quantity,
        limit_price=limit_price,
        stop_price=stop_price,
    )


def create_repository(
    tmp_path: Path,
    *,
    times: list[datetime] | None = None,
) -> tuple[
    Path,
    OrderRepository,
]:
    """シグナル登録済みDBと注文Repositoryを作成する。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    SignalRepository(
        database_path,
        now_provider=lambda: CREATED_AT,
    ).save(
        create_signal()
    )

    repository = OrderRepository(
        database_path,
        now_provider=SequentialClock(
            times or [CREATED_AT]
        ).now,
    )

    return database_path, repository


def test_initialize_database_creates_trade_orders_table(
    tmp_path: Path,
) -> None:
    """DB初期化でtrade_ordersを作成する。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        table_row = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'trade_orders'
            """
        ).fetchone()

        version_row = connection.execute(
            """
            SELECT version
            FROM schema_version
            WHERE id = 1
            """
        ).fetchone()

    assert table_row == (
        "trade_orders",
    )
    assert version_row == (
        SCHEMA_VERSION,
    )
    assert SCHEMA_VERSION == 9


def test_repository_creates_new_order(
    tmp_path: Path,
) -> None:
    """注文をNEW状態で保存する。"""

    _database_path, repository = create_repository(
        tmp_path
    )

    order = create_order()
    record = repository.create(order)

    assert record.id > 0
    assert record.order == order
    assert record.status is OrderStatus.NEW
    assert record.filled_quantity == 0
    assert record.remaining_quantity == 100
    assert record.average_fill_price is None
    assert record.broker_order_id is None
    assert record.created_at == CREATED_AT
    assert record.updated_at == CREATED_AT
    assert record.submitted_at is None
    assert record.completed_at is None

    assert repository.get(
        "order-001"
    ) == record

    assert repository.get_by_signal_id(
        "signal-001"
    ) == record


def test_repository_rejects_duplicate_order_id(
    tmp_path: Path,
) -> None:
    """同一注文IDの重複を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            CREATED_AT,
            QUEUED_AT,
        ],
    )

    repository.create(
        create_order()
    )

    with pytest.raises(
        DuplicateOrderError,
        match="既に使用",
    ):
        repository.create(
            create_order(
                signal_id="signal-001",
            )
        )


def test_repository_rejects_second_order_for_signal(
    tmp_path: Path,
) -> None:
    """1つのシグナルから複数注文を作成できない。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            CREATED_AT,
            QUEUED_AT,
        ],
    )

    repository.create(
        create_order(
            order_id="order-001",
        )
    )

    with pytest.raises(
        DuplicateOrderError,
        match="シグナルID",
    ):
        repository.create(
            create_order(
                order_id="order-002",
            )
        )


def test_repository_rejects_unknown_signal(
    tmp_path: Path,
) -> None:
    """存在しないシグナルからの注文作成を拒否する。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    repository = OrderRepository(
        database_path,
        now_provider=lambda: CREATED_AT,
    )

    with pytest.raises(
        DuplicateOrderError,
    ):
        repository.create(
            create_order(
                signal_id="missing-signal",
            )
        )


def test_repository_transitions_to_queued_and_sent(
    tmp_path: Path,
) -> None:
    """NEWからQUEUED、SENTへ遷移する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            CREATED_AT,
            QUEUED_AT,
            SENT_AT,
        ],
    )

    repository.create(
        create_order()
    )

    queued = repository.transition(
        "order-001",
        target_status=OrderStatus.QUEUED,
        status_reason="risk approved",
    )

    assert queued.status is OrderStatus.QUEUED
    assert queued.status_reason == "risk approved"
    assert queued.submitted_at is None

    sent = repository.transition(
        "order-001",
        target_status=OrderStatus.SENT,
        broker_order_id="broker-001",
        status_reason="broker accepted",
    )

    assert sent.status is OrderStatus.SENT
    assert sent.broker_order_id == "broker-001"
    assert sent.submitted_at == SENT_AT
    assert sent.completed_at is None


def test_repository_records_partial_and_full_fill(
    tmp_path: Path,
) -> None:
    """部分約定後に全約定へ遷移する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            CREATED_AT,
            QUEUED_AT,
            SENT_AT,
            PARTIAL_AT,
            FILLED_AT,
        ],
    )

    repository.create(
        create_order()
    )

    repository.transition(
        "order-001",
        target_status=OrderStatus.QUEUED,
    )
    repository.transition(
        "order-001",
        target_status=OrderStatus.SENT,
        broker_order_id="broker-001",
    )

    partial = repository.transition(
        "order-001",
        target_status=OrderStatus.PARTIALLY_FILLED,
        filled_quantity=40,
        average_fill_price=2501.0,
    )

    assert partial.filled_quantity == 40
    assert partial.remaining_quantity == 60
    assert partial.average_fill_price == pytest.approx(
        2501.0
    )

    filled = repository.transition(
        "order-001",
        target_status=OrderStatus.FILLED,
        filled_quantity=100,
        average_fill_price=2502.5,
    )

    assert filled.status is OrderStatus.FILLED
    assert filled.filled_quantity == 100
    assert filled.remaining_quantity == 0
    assert filled.average_fill_price == pytest.approx(
        2502.5
    )
    assert filled.completed_at == FILLED_AT


def test_repository_cancels_sent_order(
    tmp_path: Path,
) -> None:
    """送信済み注文を取消済みにする。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            CREATED_AT,
            QUEUED_AT,
            SENT_AT,
            FILLED_AT,
        ],
    )

    repository.create(
        create_order()
    )
    repository.transition(
        "order-001",
        target_status=OrderStatus.QUEUED,
    )
    repository.transition(
        "order-001",
        target_status=OrderStatus.SENT,
    )

    cancelled = repository.transition(
        "order-001",
        target_status=OrderStatus.CANCELLED,
        status_reason="user cancelled",
    )

    assert cancelled.status is OrderStatus.CANCELLED
    assert cancelled.status_reason == "user cancelled"
    assert cancelled.completed_at == FILLED_AT


def test_repository_records_rejection(
    tmp_path: Path,
) -> None:
    """証券会社の注文拒否を保存する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            CREATED_AT,
            QUEUED_AT,
            SENT_AT,
        ],
    )

    repository.create(
        create_order()
    )
    repository.transition(
        "order-001",
        target_status=OrderStatus.QUEUED,
    )

    rejected = repository.transition(
        "order-001",
        target_status=OrderStatus.REJECTED,
        error_message="insufficient buying power",
    )

    assert rejected.status is OrderStatus.REJECTED
    assert rejected.error_message == (
        "insufficient buying power"
    )
    assert rejected.completed_at == SENT_AT


def test_repository_rejects_invalid_transition(
    tmp_path: Path,
) -> None:
    """NEWからFILLEDへの直接遷移を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path
    )

    repository.create(
        create_order()
    )

    with pytest.raises(
        OrderStateTransitionError,
        match="許可されていない",
    ):
        repository.transition(
            "order-001",
            target_status=OrderStatus.FILLED,
            filled_quantity=100,
            average_fill_price=2500.0,
        )


def test_repository_rejects_transition_from_terminal_status(
    tmp_path: Path,
) -> None:
    """終了状態からの再遷移を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            CREATED_AT,
            QUEUED_AT,
        ],
    )

    repository.create(
        create_order()
    )
    repository.transition(
        "order-001",
        target_status=OrderStatus.CANCELLED,
    )

    with pytest.raises(
        OrderStateTransitionError,
        match="許可されていない",
    ):
        repository.transition(
            "order-001",
            target_status=OrderStatus.QUEUED,
        )


def test_repository_filters_orders(
    tmp_path: Path,
) -> None:
    """状態・銘柄・売買方向で注文を絞り込む。"""

    _database_path, repository = create_repository(
        tmp_path
    )

    repository.create(
        create_order()
    )

    records = repository.list_recent(
        code="7203",
        status=OrderStatus.NEW,
        side=OrderSide.BUY,
    )

    assert [
        record.order_id
        for record in records
    ] == [
        "order-001",
    ]

    assert repository.count(
        status=OrderStatus.NEW,
    ) == 1


def test_repository_returns_none_without_signal_order(
    tmp_path: Path,
) -> None:
    """注文がないシグナルにはNoneを返す。"""

    _database_path, repository = create_repository(
        tmp_path
    )

    assert repository.get_by_signal_id(
        "signal-001"
    ) is None
    assert repository.count() == 0


def test_repository_rejects_missing_order(
    tmp_path: Path,
) -> None:
    """存在しない注文IDを拒否する。"""

    _database_path, repository = create_repository(
        tmp_path
    )

    with pytest.raises(
        OrderNotFoundError,
        match="存在しません",
    ):
        repository.get(
            "missing-order"
        )


@pytest.mark.parametrize(
    (
        "arguments",
        "message",
    ),
    [
        (
            {
                "order_id": " ",
            },
            "注文ID",
        ),
        (
            {
                "signal_id": " ",
            },
            "シグナルID",
        ),
        (
            {
                "code": "ABC",
            },
            "数字",
        ),
        (
            {
                "quantity": 0,
            },
            "注文数量",
        ),
        (
            {
                "order_type": OrderType.LIMIT,
                "limit_price": None,
            },
            "指値価格",
        ),
        (
            {
                "order_type": OrderType.STOP,
                "stop_price": None,
            },
            "逆指値価格",
        ),
        (
            {
                "order_type": OrderType.MARKET,
                "limit_price": 2500.0,
            },
            "成行注文",
        ),
    ],
)
def test_trade_order_rejects_invalid_values(
    arguments: dict[str, object],
    message: str,
) -> None:
    """不正な注文内容を拒否する。"""

    base_arguments: dict[str, object] = {
        "order_id": "order-001",
        "signal_id": "signal-001",
        "code": "7203",
        "side": OrderSide.BUY,
        "order_type": OrderType.MARKET,
        "quantity": 100,
    }

    base_arguments.update(arguments)

    with pytest.raises(
        (
            TypeError,
            ValueError,
        ),
        match=message,
    ):
        TradeOrder(
            **base_arguments
        )