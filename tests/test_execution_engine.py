"""Execution Engineのシグナル・注文・Broker統合テスト。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.database import initialize_database
from app.trading.execution_engine import (
    ExecutionDecision,
    ExecutionEngine,
)
from app.trading.order_broker_sync_service import (
    OrderBrokerSyncService,
)
from app.trading.order_models import (
    OrderStatus,
    OrderType,
)
from app.trading.order_repository import (
    OrderRepository,
)
from app.trading.order_service import (
    SignalOrderService,
)
from app.trading.paper_broker import (
    PaperBroker,
    PaperBrokerSettings,
)
from app.trading.signal_models import (
    SignalAction,
    SignalStatus,
    TradeSignal,
)
from app.trading.signal_repository import (
    SignalRepository,
)


BASE_TIME = datetime(
    2026,
    7,
    16,
    0,
    30,
    tzinfo=timezone.utc,
)


def create_signal(
    *,
    signal_id: str = "signal-001",
    code: str = "7203",
    generated_at: datetime = BASE_TIME,
    quantity: int = 100,
) -> TradeSignal:
    """Execution Engine用シグナルを作成する。"""

    return TradeSignal(
        signal_id=signal_id,
        code=code,
        strategy_name="orb",
        action=SignalAction.BUY,
        generated_at=generated_at,
        signal_price=2500.0,
        quantity=quantity,
        reason="opening_range_breakout",
        confidence=0.8,
    )


def create_environment(
    tmp_path: Path,
    *,
    initial_cash: float = 1_000_000.0,
    market_price: float = 2500.0,
) -> tuple[
    SignalRepository,
    OrderRepository,
    PaperBroker,
    ExecutionEngine,
]:
    """実SQLiteとPaperBrokerを使う実行環境を作成する。"""

    database_path = tmp_path / "katana.db"

    initialize_database(
        database_path,
    )

    signal_repository = SignalRepository(
        database_path,
        now_provider=lambda: BASE_TIME,
    )

    order_repository = OrderRepository(
        database_path,
        now_provider=lambda: BASE_TIME,
    )

    order_service = SignalOrderService(
        signal_repository=signal_repository,
        order_repository=order_repository,
    )

    broker = PaperBroker(
        settings=PaperBrokerSettings(
            initial_cash=initial_cash,
        ),
        price_provider=lambda _code: market_price,
        now_provider=lambda: BASE_TIME,
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

    return (
        signal_repository,
        order_repository,
        broker,
        engine,
    )


def test_engine_executes_pending_market_signal(
    tmp_path: Path,
) -> None:
    """未処理BUYシグナルを成行注文として全約定する。"""

    (
        signal_repository,
        order_repository,
        broker,
        engine,
    ) = create_environment(
        tmp_path
    )

    signal_repository.save(
        create_signal()
    )

    result = engine.run_pending()

    assert result.input_count == 1
    assert result.executed_count == 1
    assert result.active_count == 0
    assert result.terminal_count == 1
    assert result.failed_count == 0
    assert result.is_successful is True

    item = result.items[0]

    assert item.decision is (
        ExecutionDecision.TERMINAL
    )
    assert item.signal_id == "signal-001"
    assert item.order_id is not None
    assert item.is_executed is True
    assert item.is_terminal is True
    assert item.message is None

    assert item.order_record is not None
    assert item.order_record.status is (
        OrderStatus.FILLED
    )
    assert item.order_record.filled_quantity == 100
    assert item.order_record.average_fill_price == (
        pytest.approx(2500.0)
    )

    assert signal_repository.count(
        status=SignalStatus.PROCESSED,
    ) == 1
    assert order_repository.count(
        status=OrderStatus.FILLED,
    ) == 1

    positions = broker.list_positions()

    assert len(positions) == 1
    assert positions[0].code == "7203"
    assert positions[0].quantity == 100


def test_engine_creates_active_limit_order(
    tmp_path: Path,
) -> None:
    """条件未到達の指値注文をSENT状態で保持する。"""

    (
        signal_repository,
        order_repository,
        broker,
        engine,
    ) = create_environment(
        tmp_path,
        market_price=2500.0,
    )

    signal_repository.save(
        create_signal()
    )

    result = engine.run_pending(
        order_type=OrderType.LIMIT,
        limit_price=2400.0,
    )

    assert result.input_count == 1
    assert result.executed_count == 1
    assert result.active_count == 1
    assert result.terminal_count == 0
    assert result.failed_count == 0

    item = result.items[0]

    assert item.decision is (
        ExecutionDecision.ACTIVE
    )
    assert item.order_record is not None
    assert item.order_record.status is (
        OrderStatus.SENT
    )
    assert item.order_record.broker_order_id is not None

    assert order_repository.count(
        status=OrderStatus.SENT,
    ) == 1
    assert broker.list_positions() == []


def test_engine_processes_signals_oldest_first(
    tmp_path: Path,
) -> None:
    """複数シグナルを生成日時の古い順に処理する。"""

    (
        signal_repository,
        _order_repository,
        broker,
        engine,
    ) = create_environment(
        tmp_path,
        initial_cash=2_000_000.0,
    )

    signal_repository.save(
        create_signal(
            signal_id="signal-later",
            code="8306",
            generated_at=(
                BASE_TIME
                + timedelta(minutes=5)
            ),
        )
    )

    signal_repository.save(
        create_signal(
            signal_id="signal-earlier",
            code="7203",
            generated_at=BASE_TIME,
        )
    )

    result = engine.run_pending()

    assert [
        item.signal_id
        for item in result.items
    ] == [
        "signal-earlier",
        "signal-later",
    ]

    assert result.input_count == 2
    assert result.terminal_count == 2
    assert len(
        broker.list_positions()
    ) == 2


def test_engine_respects_processing_limit(
    tmp_path: Path,
) -> None:
    """指定件数まで未処理シグナルを実行する。"""

    (
        signal_repository,
        order_repository,
        _broker,
        engine,
    ) = create_environment(
        tmp_path,
        initial_cash=2_000_000.0,
    )

    for index, code in enumerate(
        [
            "7203",
            "8306",
            "6758",
        ]
    ):
        signal_repository.save(
            create_signal(
                signal_id=(
                    f"signal-{index + 1}"
                ),
                code=code,
                generated_at=(
                    BASE_TIME
                    + timedelta(minutes=index)
                ),
            )
        )

    result = engine.run_pending(
        limit=2,
    )

    assert result.input_count == 2
    assert order_repository.count() == 2
    assert signal_repository.count(
        status=SignalStatus.PENDING,
    ) == 1


def test_engine_filters_pending_signals_by_code(
    tmp_path: Path,
) -> None:
    """銘柄コードを指定して未処理シグナルを実行する。"""

    (
        signal_repository,
        order_repository,
        _broker,
        engine,
    ) = create_environment(
        tmp_path,
        initial_cash=2_000_000.0,
    )

    signal_repository.save(
        create_signal(
            signal_id="signal-7203",
            code="7203",
        )
    )

    signal_repository.save(
        create_signal(
            signal_id="signal-8306",
            code="8306",
            generated_at=(
                BASE_TIME
                + timedelta(minutes=1)
            ),
        )
    )

    result = engine.run_pending(
        code="8306",
    )

    assert result.input_count == 1
    assert result.items[0].signal_id == (
        "signal-8306"
    )
    assert order_repository.count(
        code="8306",
    ) == 1
    assert signal_repository.count(
        status=SignalStatus.PENDING,
    ) == 1


def test_engine_returns_empty_result_without_pending_signals(
    tmp_path: Path,
) -> None:
    """未処理シグナルがなければ空の正常結果を返す。"""

    (
        _signal_repository,
        order_repository,
        broker,
        engine,
    ) = create_environment(
        tmp_path
    )

    result = engine.run_pending()

    assert result.input_count == 0
    assert result.executed_count == 0
    assert result.active_count == 0
    assert result.terminal_count == 0
    assert result.failed_count == 0
    assert result.order_records == ()
    assert result.is_successful is True

    assert order_repository.count() == 0
    assert broker.list_orders() == []


def test_engine_does_not_reexecute_processed_signal(
    tmp_path: Path,
) -> None:
    """同じEngineを再実行しても二重発注しない。"""

    (
        signal_repository,
        order_repository,
        broker,
        engine,
    ) = create_environment(
        tmp_path
    )

    signal_repository.save(
        create_signal()
    )

    first = engine.run_pending()
    second = engine.run_pending()

    assert first.input_count == 1
    assert first.terminal_count == 1

    assert second.input_count == 0
    assert second.is_successful is True

    assert order_repository.count() == 1
    assert len(broker.list_orders()) == 1
    assert broker.list_positions()[0].quantity == 100


def test_execute_signal_can_reconcile_existing_order(
    tmp_path: Path,
) -> None:
    """既存注文があるシグナルを冪等に再同期する。"""

    (
        signal_repository,
        order_repository,
        broker,
        engine,
    ) = create_environment(
        tmp_path
    )

    signal_repository.save(
        create_signal()
    )

    first = engine.execute_signal(
        "signal-001"
    )
    second = engine.execute_signal(
        "signal-001"
    )

    assert first.order_id == second.order_id
    assert first.order_record is not None
    assert second.order_record is not None
    assert second.order_record.status is (
        OrderStatus.FILLED
    )

    assert order_repository.count() == 1
    assert len(broker.list_orders()) == 1
    assert broker.list_positions()[0].quantity == 100


def test_engine_records_failure_and_continues(
    tmp_path: Path,
) -> None:
    """1件の買付余力不足を記録し後続処理を継続する。"""

    (
        signal_repository,
        order_repository,
        broker,
        engine,
    ) = create_environment(
        tmp_path,
        initial_cash=300_000.0,
        market_price=2500.0,
    )

    signal_repository.save(
        create_signal(
            signal_id="signal-large",
            code="7203",
            generated_at=BASE_TIME,
            quantity=200,
        )
    )

    signal_repository.save(
        create_signal(
            signal_id="signal-small",
            code="8306",
            generated_at=(
                BASE_TIME
                + timedelta(minutes=1)
            ),
            quantity=100,
        )
    )

    result = engine.run_pending(
        continue_on_error=True,
    )

    assert result.input_count == 2
    assert result.failed_count == 1
    assert result.terminal_count == 1
    assert result.is_successful is False

    failed_item = result.items[0]

    assert failed_item.signal_id == (
        "signal-large"
    )
    assert failed_item.is_failed is True
    assert "買付余力" in (
        failed_item.message or ""
    )

    successful_item = result.items[1]

    assert successful_item.signal_id == (
        "signal-small"
    )
    assert successful_item.is_terminal is True

    assert order_repository.count(
        status=OrderStatus.FAILED,
    ) == 1
    assert order_repository.count(
        status=OrderStatus.FILLED,
    ) == 1

    assert len(
        broker.list_positions()
    ) == 1


def test_engine_raises_failure_when_continuation_disabled(
    tmp_path: Path,
) -> None:
    """continue_on_error無効時は執行例外を再送出する。"""

    (
        signal_repository,
        _order_repository,
        _broker,
        engine,
    ) = create_environment(
        tmp_path,
        initial_cash=100_000.0,
    )

    signal_repository.save(
        create_signal()
    )

    with pytest.raises(
        Exception,
        match="買付余力",
    ):
        engine.run_pending(
            continue_on_error=False,
        )


def test_engine_rejects_invalid_limit() -> None:
    """0以下の処理件数を拒否する。"""

    class EmptySignalRepository:
        """未処理シグナルを持たないRepository。"""

        def list_pending(
            self,
            *,
            limit: int = 100,
            code: str | None = None,
            strategy_name: str | None = None,
        ):
            """空一覧を返す。"""

            del limit
            del code
            del strategy_name

            return []

    engine = ExecutionEngine(
        signal_repository=EmptySignalRepository(),
        order_service=object(),
        broker_sync_service=object(),
    )

    with pytest.raises(
        ValueError,
        match="処理件数",
    ):
        engine.run_pending(
            limit=0,
        )


def test_engine_rejects_empty_signal_id(
    tmp_path: Path,
) -> None:
    """空のシグナルIDを拒否する。"""

    (
        _signal_repository,
        _order_repository,
        _broker,
        engine,
    ) = create_environment(
        tmp_path
    )

    with pytest.raises(
        ValueError,
        match="シグナルID",
    ):
        engine.execute_signal(
            " "
        )