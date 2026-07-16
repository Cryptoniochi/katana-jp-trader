"""PositionServiceの統合テスト。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.database import initialize_database
from app.trading.broker_adapter import BrokerPositionSide
from app.trading.order_models import OrderSide
from app.trading.position_repository import PositionRepository
from app.trading.position_service import (
    InsufficientPositionError,
    PositionService,
)
from app.trading.trade_execution_models import (
    TradeExecution,
    TradeExecutionRecord,
)


BASE_TIME = datetime(
    2026,
    7,
    20,
    0,
    30,
    tzinfo=timezone.utc,
)


class SequentialClock:
    """指定日時を順番に返す時計。"""

    def __init__(self, values: list[datetime]) -> None:
        self.values = iter(values)

    def now(self) -> datetime:
        return next(self.values)


def create_execution_record(
    *,
    record_id: int,
    execution_id: str,
    side: OrderSide,
    quantity: int,
    execution_price: float,
    executed_at: datetime,
) -> TradeExecutionRecord:
    """テスト用約定レコードを作成する。"""

    execution = TradeExecution(
        execution_id=execution_id,
        signal_id=f"signal-{execution_id}",
        order_id=f"order-{execution_id}",
        broker_order_id=f"broker-{execution_id}",
        code="7203",
        side=side,
        quantity=quantity,
        execution_price=execution_price,
        executed_at=executed_at,
        broker_name="paper",
    )

    return TradeExecutionRecord(
        id=record_id,
        execution=execution,
        created_at=executed_at,
        updated_at=executed_at,
    )


def create_service(
    tmp_path: Path,
    *,
    times: list[datetime],
) -> tuple[PositionRepository, PositionService]:
    """RepositoryとPositionServiceを作成する。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    repository = PositionRepository(
        database_path,
        now_provider=SequentialClock(times).now,
    )
    service = PositionService(
        database_path=database_path,
        position_repository=repository,
    )

    return repository, service


def test_service_creates_position_from_buy(
    tmp_path: Path,
) -> None:
    """最初の買い約定で新規ポジションを作成する。"""

    repository, service = create_service(
        tmp_path,
        times=[BASE_TIME],
    )

    result = service.apply_execution(
        create_execution_record(
            record_id=1,
            execution_id="execution-buy-1",
            side=OrderSide.BUY,
            quantity=100,
            execution_price=2500.0,
            executed_at=BASE_TIME,
        )
    )

    assert result.applied
    assert not result.position_closed
    assert result.position_record is not None
    assert result.position_record.quantity == 100
    assert result.position_record.position.average_cost == pytest.approx(
        2500.0
    )
    assert repository.count() == 1


def test_service_averages_additional_buy(
    tmp_path: Path,
) -> None:
    """買い増し時に加重平均取得価格を計算する。"""

    repository, service = create_service(
        tmp_path,
        times=[
            BASE_TIME,
            BASE_TIME + timedelta(minutes=1),
        ],
    )

    service.apply_execution(
        create_execution_record(
            record_id=1,
            execution_id="execution-buy-1",
            side=OrderSide.BUY,
            quantity=100,
            execution_price=2500.0,
            executed_at=BASE_TIME,
        )
    )
    result = service.apply_execution(
        create_execution_record(
            record_id=2,
            execution_id="execution-buy-2",
            side=OrderSide.BUY,
            quantity=100,
            execution_price=2600.0,
            executed_at=BASE_TIME + timedelta(minutes=1),
        )
    )

    assert result.position_record is not None
    assert result.position_record.quantity == 200
    assert result.position_record.position.average_cost == pytest.approx(
        2550.0
    )
    assert repository.count() == 1


def test_service_partially_sells_position(
    tmp_path: Path,
) -> None:
    """一部売却で数量を減らし実現損益を加算する。"""

    repository, service = create_service(
        tmp_path,
        times=[
            BASE_TIME,
            BASE_TIME + timedelta(minutes=1),
        ],
    )

    service.apply_execution(
        create_execution_record(
            record_id=1,
            execution_id="execution-buy",
            side=OrderSide.BUY,
            quantity=100,
            execution_price=2500.0,
            executed_at=BASE_TIME,
        )
    )
    result = service.apply_execution(
        create_execution_record(
            record_id=2,
            execution_id="execution-sell",
            side=OrderSide.SELL,
            quantity=40,
            execution_price=2700.0,
            executed_at=BASE_TIME + timedelta(minutes=1),
        )
    )

    assert result.position_record is not None
    assert result.position_record.quantity == 60
    assert result.realized_profit_loss == pytest.approx(8000.0)
    assert (
        result.position_record.position.realized_profit_loss
        == pytest.approx(8000.0)
    )
    assert repository.count() == 1


def test_service_closes_position_on_full_sell(
    tmp_path: Path,
) -> None:
    """全売却で現在ポジションを削除する。"""

    repository, service = create_service(
        tmp_path,
        times=[BASE_TIME],
    )

    service.apply_execution(
        create_execution_record(
            record_id=1,
            execution_id="execution-buy",
            side=OrderSide.BUY,
            quantity=100,
            execution_price=2500.0,
            executed_at=BASE_TIME,
        )
    )
    result = service.apply_execution(
        create_execution_record(
            record_id=2,
            execution_id="execution-sell",
            side=OrderSide.SELL,
            quantity=100,
            execution_price=2700.0,
            executed_at=BASE_TIME + timedelta(minutes=1),
        )
    )

    assert result.position_closed
    assert result.position_record is None
    assert result.realized_profit_loss == pytest.approx(20_000.0)
    assert repository.count() == 0


def test_service_rejects_sell_without_position(
    tmp_path: Path,
) -> None:
    """ポジションがない売却を拒否する。"""

    _repository, service = create_service(
        tmp_path,
        times=[],
    )

    with pytest.raises(
        InsufficientPositionError,
        match="存在しません",
    ):
        service.apply_execution(
            create_execution_record(
                record_id=1,
                execution_id="execution-sell",
                side=OrderSide.SELL,
                quantity=100,
                execution_price=2700.0,
                executed_at=BASE_TIME,
            )
        )


def test_service_rejects_oversell(
    tmp_path: Path,
) -> None:
    """保有数量を超える売却を拒否する。"""

    repository, service = create_service(
        tmp_path,
        times=[BASE_TIME],
    )

    service.apply_execution(
        create_execution_record(
            record_id=1,
            execution_id="execution-buy",
            side=OrderSide.BUY,
            quantity=100,
            execution_price=2500.0,
            executed_at=BASE_TIME,
        )
    )

    with pytest.raises(
        InsufficientPositionError,
        match="超えています",
    ):
        service.apply_execution(
            create_execution_record(
                record_id=2,
                execution_id="execution-sell",
                side=OrderSide.SELL,
                quantity=101,
                execution_price=2700.0,
                executed_at=BASE_TIME + timedelta(minutes=1),
            )
        )

    assert repository.get_by_identity(
        code="7203",
        side=BrokerPositionSide.LONG,
    ).quantity == 100


def test_service_does_not_apply_same_execution_twice(
    tmp_path: Path,
) -> None:
    """同じ約定を再実行しても数量を二重加算しない。"""

    repository, service = create_service(
        tmp_path,
        times=[BASE_TIME],
    )
    execution = create_execution_record(
        record_id=1,
        execution_id="execution-buy",
        side=OrderSide.BUY,
        quantity=100,
        execution_price=2500.0,
        executed_at=BASE_TIME,
    )

    first = service.apply_execution(execution)
    second = service.apply_execution(execution)

    assert first.applied
    assert not second.applied
    assert repository.get_by_identity(
        code="7203",
        side=BrokerPositionSide.LONG,
    ).quantity == 100
