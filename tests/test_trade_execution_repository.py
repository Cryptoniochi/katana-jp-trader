"""約定履歴モデルとRepositoryのテスト。"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.database import SCHEMA_VERSION, initialize_database
from app.trading.order_models import (
    OrderSide,
    OrderType,
    TradeOrder,
)
from app.trading.order_repository import OrderRepository
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)
from app.trading.signal_repository import SignalRepository
from app.trading.trade_execution_models import TradeExecution
from app.trading.trade_execution_repository import (
    DuplicateTradeExecutionError,
    TradeExecutionNotFoundError,
    TradeExecutionRepository,
)


CREATED_AT = datetime(
    2026,
    7,
    20,
    0,
    30,
    tzinfo=timezone.utc,
)


def create_execution(
    *,
    execution_id: str = "execution-001",
    signal_id: str = "signal-001",
    order_id: str = "order-001",
    code: str = "7203",
    side: OrderSide = OrderSide.BUY,
    quantity: int = 100,
    execution_price: float = 2500.0,
    executed_at: datetime = CREATED_AT,
) -> TradeExecution:
    return TradeExecution(
        execution_id=execution_id,
        signal_id=signal_id,
        order_id=order_id,
        broker_order_id="paper-order-00000001",
        code=code,
        side=side,
        quantity=quantity,
        execution_price=execution_price,
        executed_at=executed_at,
        broker_name="paper",
        commission=100.0,
        slippage=50.0,
        metadata={"source": "paper-broker"},
    )


def create_repository(
    tmp_path: Path,
) -> tuple[Path, TradeExecutionRepository]:
    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    SignalRepository(
        database_path,
        now_provider=lambda: CREATED_AT,
    ).save(
        TradeSignal(
            signal_id="signal-001",
            code="7203",
            strategy_name="orb",
            action=SignalAction.BUY,
            generated_at=CREATED_AT,
            signal_price=2500.0,
            quantity=100,
            reason="opening_range_breakout",
        )
    )

    OrderRepository(
        database_path,
        now_provider=lambda: CREATED_AT,
    ).create(
        TradeOrder(
            order_id="order-001",
            signal_id="signal-001",
            code="7203",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
        )
    )

    return (
        database_path,
        TradeExecutionRepository(
            database_path,
            now_provider=lambda: CREATED_AT,
        ),
    )


def test_initialize_database_creates_trade_executions_table(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        table_row = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'trade_executions'
            """
        ).fetchone()
        version_row = connection.execute(
            """
            SELECT version
            FROM schema_version
            WHERE id = 1
            """
        ).fetchone()

    assert table_row == ("trade_executions",)
    assert version_row == (SCHEMA_VERSION,)
    assert SCHEMA_VERSION == 7


def test_repository_saves_and_reads_execution(
    tmp_path: Path,
) -> None:
    _database_path, repository = create_repository(tmp_path)

    execution = create_execution()
    record = repository.save(execution)

    assert record.id > 0
    assert record.execution == execution
    assert record.created_at == CREATED_AT
    assert record.updated_at == CREATED_AT
    assert record.execution.gross_value == pytest.approx(250_000.0)
    assert record.execution.total_cost == pytest.approx(150.0)
    assert repository.get("execution-001") == record


def test_repository_rejects_duplicate_execution_id(
    tmp_path: Path,
) -> None:
    _database_path, repository = create_repository(tmp_path)
    repository.save(create_execution())

    with pytest.raises(
        DuplicateTradeExecutionError,
        match="約定ID",
    ):
        repository.save(create_execution())


def test_repository_rejects_unknown_order(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    repository = TradeExecutionRepository(
        database_path,
        now_provider=lambda: CREATED_AT,
    )

    with pytest.raises(DuplicateTradeExecutionError):
        repository.save(create_execution())


def test_repository_lists_and_filters_executions(
    tmp_path: Path,
) -> None:
    _database_path, repository = create_repository(tmp_path)
    repository.save(create_execution())

    assert len(repository.list_recent(code="7203")) == 1
    assert len(repository.list_recent(side=OrderSide.BUY)) == 1
    assert len(repository.find_by_order("order-001")) == 1
    assert len(repository.find_by_signal("signal-001")) == 1
    assert repository.count(code="7203") == 1
    assert repository.count(order_id="order-001") == 1
    assert repository.count(signal_id="signal-001") == 1


def test_repository_returns_latest_execution(
    tmp_path: Path,
) -> None:
    _database_path, repository = create_repository(tmp_path)
    record = repository.save(create_execution())

    assert repository.latest() == record
    assert repository.latest(code="8306") is None


def test_repository_rejects_missing_execution(
    tmp_path: Path,
) -> None:
    _database_path, repository = create_repository(tmp_path)

    with pytest.raises(
        TradeExecutionNotFoundError,
        match="存在しません",
    ):
        repository.get("missing-execution")


def test_repository_rejects_invalid_limit(
    tmp_path: Path,
) -> None:
    _database_path, repository = create_repository(tmp_path)

    with pytest.raises(ValueError, match="取得件数"):
        repository.list_recent(limit=0)


def test_repository_normalizes_executed_at_to_utc(
    tmp_path: Path,
) -> None:
    _database_path, repository = create_repository(tmp_path)
    jst = timezone(timedelta(hours=9))

    record = repository.save(
        create_execution(
            executed_at=datetime(
                2026,
                7,
                20,
                9,
                30,
                tzinfo=jst,
            )
        )
    )

    assert record.execution.executed_at == CREATED_AT


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"execution_id": " "}, "約定ID"),
        ({"code": "ABC"}, "数字"),
        ({"quantity": 0}, "約定数量"),
        ({"execution_price": 0.0}, "約定価格"),
        ({"commission": -1.0}, "手数料"),
        ({"slippage": -1.0}, "スリッページ"),
    ],
)
def test_execution_rejects_invalid_values(
    arguments: dict[str, object],
    message: str,
) -> None:
    base_arguments: dict[str, object] = {
        "execution_id": "execution-001",
        "signal_id": "signal-001",
        "order_id": "order-001",
        "broker_order_id": "paper-order-00000001",
        "code": "7203",
        "side": OrderSide.BUY,
        "quantity": 100,
        "execution_price": 2500.0,
        "executed_at": CREATED_AT,
        "broker_name": "paper",
        "commission": 0.0,
        "slippage": 0.0,
        "metadata": {},
    }
    base_arguments.update(arguments)

    with pytest.raises((TypeError, ValueError), match=message):
        TradeExecution(**base_arguments)


def test_execution_rejects_naive_executed_at() -> None:
    with pytest.raises(ValueError, match="タイムゾーン"):
        create_execution(
            executed_at=datetime(
                2026,
                7,
                20,
                9,
                30,
            )
        )
