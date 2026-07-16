"""TradeExecutionServiceの統合テスト。"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.database import initialize_database
from app.trading.execution_engine import ExecutionEngine
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
from app.trading.trade_execution_service import (
    TradeExecutionService,
)


CURRENT_TIME = datetime(
    2026,
    7,
    20,
    0,
    30,
    tzinfo=timezone.utc,
)


def create_environment(
    tmp_path: Path,
    *,
    market_price: float = 2500.0,
    commission: float = 0.0,
    slippage_rate: float = 0.0,
) -> tuple[
    SignalRepository,
    OrderRepository,
    TradeExecutionRepository,
    PaperBroker,
    TradeExecutionService,
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

    broker = PaperBroker(
        price_provider=lambda _code: market_price,
        settings=PaperBrokerSettings(
            initial_cash=1_000_000.0,
            commission_per_order=commission,
            slippage_rate=slippage_rate,
        ),
        now_provider=lambda: CURRENT_TIME,
    )

    sync_service = OrderBrokerSyncService(
        order_repository=order_repository,
        broker=broker,
    )

    engine = ExecutionEngine(
        signal_repository=signal_repository,
        order_service=order_service,
        broker_sync_service=sync_service,
    )

    service = TradeExecutionService(
        execution_engine=engine,
        execution_repository=execution_repository,
        broker_name=broker.broker_name,
        commission_per_execution=commission,
    )

    return (
        signal_repository,
        order_repository,
        execution_repository,
        broker,
        service,
    )


def create_signal() -> TradeSignal:
    """標準的なBUYシグナルを作成する。"""

    return TradeSignal(
        signal_id="signal-001",
        code="7203",
        strategy_name="orb",
        action=SignalAction.BUY,
        generated_at=CURRENT_TIME,
        signal_price=2500.0,
        quantity=100,
        reason="opening_range_breakout",
    )


def test_service_saves_filled_market_execution(
    tmp_path: Path,
) -> None:
    """全約定した成行注文を約定台帳へ保存する。"""

    (
        signal_repository,
        order_repository,
        execution_repository,
        _broker,
        service,
    ) = create_environment(tmp_path)

    signal_repository.save(create_signal())

    result = service.run_pending()

    assert result.is_successful
    assert result.saved_execution_count == 1
    assert execution_repository.count() == 1

    record = result.execution_records[0]

    assert record.execution.signal_id == "signal-001"
    assert record.execution.code == "7203"
    assert record.execution.quantity == 100
    assert record.execution.execution_price == pytest.approx(
        2500.0
    )
    assert record.execution.executed_at == CURRENT_TIME
    assert record.execution.broker_name == "paper"

    assert order_repository.count(
        status=OrderStatus.FILLED,
    ) == 1


def test_service_does_not_save_unfilled_order(
    tmp_path: Path,
) -> None:
    """未約定の指値注文は約定台帳へ保存しない。"""

    (
        signal_repository,
        _order_repository,
        execution_repository,
        _broker,
        service,
    ) = create_environment(
        tmp_path,
        market_price=2500.0,
    )

    signal_repository.save(create_signal())

    result = service.run_pending(
        order_type=OrderType.LIMIT,
        limit_price=2400.0,
    )

    assert result.is_successful
    assert result.saved_execution_count == 0
    assert execution_repository.count() == 0


def test_service_is_idempotent_after_repeated_run(
    tmp_path: Path,
) -> None:
    """同じ処理を再実行しても約定を二重保存しない。"""

    (
        signal_repository,
        _order_repository,
        execution_repository,
        broker,
        service,
    ) = create_environment(tmp_path)

    signal_repository.save(create_signal())

    first = service.run_pending()
    second = service.run_pending()

    assert first.saved_execution_count == 1
    assert second.saved_execution_count == 0
    assert execution_repository.count() == 1
    assert len(broker.list_orders()) == 1
    assert broker.list_positions()[0].quantity == 100


def test_service_records_commission(
    tmp_path: Path,
) -> None:
    """設定された手数料を約定履歴へ保存する。"""

    (
        signal_repository,
        _order_repository,
        _execution_repository,
        _broker,
        service,
    ) = create_environment(
        tmp_path,
        commission=150.0,
    )

    signal_repository.save(create_signal())

    result = service.run_pending()
    execution = result.execution_records[0].execution

    assert execution.commission == pytest.approx(150.0)
    assert execution.total_cost == pytest.approx(150.0)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"broker_name": " "}, "Broker名"),
        (
            {"commission_per_execution": -1.0},
            "約定手数料",
        ),
        (
            {"slippage_per_execution": -1.0},
            "約定スリッページ",
        ),
    ],
)
def test_service_rejects_invalid_settings(
    tmp_path: Path,
    arguments: dict[str, object],
    message: str,
) -> None:
    """不正なサービス設定を拒否する。"""

    (
        _signal_repository,
        _order_repository,
        execution_repository,
        _broker,
        service,
    ) = create_environment(tmp_path)

    base_arguments: dict[str, object] = {
        "execution_engine": service.execution_engine,
        "execution_repository": execution_repository,
        "broker_name": "paper",
    }
    base_arguments.update(arguments)

    with pytest.raises(ValueError, match=message):
        TradeExecutionService(**base_arguments)
