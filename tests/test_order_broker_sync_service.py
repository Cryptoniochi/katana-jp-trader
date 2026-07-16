"""OrderRepositoryとBroker状態の同期サービステスト。"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.database import initialize_database
from app.trading.broker_adapter import (
    BrokerOrderSnapshot,
)
from app.trading.order_broker_sync_service import (
    OrderBrokerConsistencyError,
    OrderBrokerStatusError,
    OrderBrokerSyncDecision,
    OrderBrokerSyncService,
)
from app.trading.order_models import (
    OrderSide,
    OrderStatus,
    OrderType,
    TradeOrder,
)
from app.trading.order_repository import (
    OrderRepository,
)
from app.trading.paper_broker import (
    PaperBroker,
    PaperBrokerSettings,
)
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)
from app.trading.signal_repository import (
    SignalRepository,
)


CURRENT_TIME = datetime(
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
) -> TradeSignal:
    """注文元シグナルを作成する。"""

    return TradeSignal(
        signal_id=signal_id,
        code="7203",
        strategy_name="orb",
        action=SignalAction.BUY,
        generated_at=CURRENT_TIME,
        signal_price=2500.0,
        quantity=100,
        reason="opening_range_breakout",
    )


def create_order(
    *,
    order_id: str = "order-001",
    signal_id: str = "signal-001",
    order_type: OrderType = OrderType.MARKET,
    limit_price: float | None = None,
) -> TradeOrder:
    """同期対象注文を作成する。"""

    return TradeOrder(
        order_id=order_id,
        signal_id=signal_id,
        code="7203",
        side=OrderSide.BUY,
        order_type=order_type,
        quantity=100,
        limit_price=limit_price,
    )


def create_environment(
    tmp_path: Path,
    *,
    market_price: float = 2500.0,
    order_type: OrderType = OrderType.MARKET,
    limit_price: float | None = None,
) -> tuple[
    OrderRepository,
    PaperBroker,
    OrderBrokerSyncService,
]:
    """実SQLiteとPaperBrokerを使用する同期環境を作成する。"""

    database_path = tmp_path / "katana.db"

    initialize_database(
        database_path,
    )

    SignalRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    ).save(
        create_signal(),
    )

    order_repository = OrderRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    )

    order_repository.create(
        create_order(
            order_type=order_type,
            limit_price=limit_price,
        )
    )

    broker = PaperBroker(
        settings=PaperBrokerSettings(
            initial_cash=1_000_000.0,
        ),
        price_provider=lambda _code: market_price,
        now_provider=lambda: CURRENT_TIME,
    )

    service = OrderBrokerSyncService(
        order_repository=order_repository,
        broker=broker,
    )

    return (
        order_repository,
        broker,
        service,
    )


def test_submit_market_order_synchronizes_fill(
    tmp_path: Path,
) -> None:
    """成行注文をBrokerへ送り全約定をSQLiteへ反映する。"""

    repository, broker, service = create_environment(
        tmp_path,
    )

    result = service.submit(
        "order-001",
    )

    assert result.decision is (
        OrderBrokerSyncDecision.SUBMITTED
    )
    assert result.was_submitted is True
    assert result.was_synchronized is True
    assert result.was_unchanged is False
    assert result.is_failed is False
    assert result.message is None

    assert result.order_record is not None
    assert result.broker_snapshot is not None

    local = result.order_record

    assert local.status is OrderStatus.FILLED
    assert local.filled_quantity == 100
    assert local.average_fill_price == pytest.approx(
        2500.0,
    )
    assert local.broker_order_id == (
        "paper-order-00000001"
    )
    assert local.completed_at == CURRENT_TIME

    assert len(broker.list_orders()) == 1
    assert repository.get(
        "order-001",
    ) == local


def test_submit_limit_order_synchronizes_sent_state(
    tmp_path: Path,
) -> None:
    """未約定指値注文をSENT状態として反映する。"""

    repository, _broker, service = create_environment(
        tmp_path,
        market_price=2500.0,
        order_type=OrderType.LIMIT,
        limit_price=2400.0,
    )

    result = service.submit(
        "order-001",
    )

    assert result.order_record is not None

    local = result.order_record

    assert local.status is OrderStatus.SENT
    assert local.filled_quantity == 0
    assert local.average_fill_price is None
    assert local.broker_order_id == (
        "paper-order-00000001"
    )
    assert repository.count(
        status=OrderStatus.SENT,
    ) == 1


def test_refresh_synchronizes_pending_limit_fill(
    tmp_path: Path,
) -> None:
    """価格更新後の指値約定をSQLiteへ同期する。"""

    repository, broker, service = create_environment(
        tmp_path,
        market_price=2500.0,
        order_type=OrderType.LIMIT,
        limit_price=2400.0,
    )

    service.submit(
        "order-001",
    )

    broker.update_market_price(
        "7203",
        2390.0,
    )

    result = service.refresh(
        "order-001",
    )

    assert result.decision is (
        OrderBrokerSyncDecision.SYNCHRONIZED
    )
    assert result.order_record is not None
    assert result.order_record.status is (
        OrderStatus.FILLED
    )
    assert result.order_record.average_fill_price == (
        pytest.approx(2390.0)
    )
    assert repository.count(
        status=OrderStatus.FILLED,
    ) == 1


def test_refresh_returns_unchanged_when_states_match(
    tmp_path: Path,
) -> None:
    """BrokerとSQLiteの状態が同じなら更新しない。"""

    _repository, _broker, service = create_environment(
        tmp_path,
        market_price=2500.0,
        order_type=OrderType.LIMIT,
        limit_price=2400.0,
    )

    service.submit(
        "order-001",
    )

    result = service.refresh(
        "order-001",
    )

    assert result.decision is (
        OrderBrokerSyncDecision.UNCHANGED
    )
    assert result.was_unchanged is True
    assert result.order_record is not None
    assert result.order_record.status is (
        OrderStatus.SENT
    )


def test_cancel_pending_broker_order(
    tmp_path: Path,
) -> None:
    """Broker側の待機注文を取り消してSQLiteへ同期する。"""

    repository, _broker, service = create_environment(
        tmp_path,
        market_price=2500.0,
        order_type=OrderType.LIMIT,
        limit_price=2400.0,
    )

    service.submit(
        "order-001",
    )

    result = service.cancel(
        "order-001",
    )

    assert result.decision is (
        OrderBrokerSyncDecision.CANCELLED
    )
    assert result.order_record is not None
    assert result.order_record.status is (
        OrderStatus.CANCELLED
    )
    assert result.order_record.completed_at == (
        CURRENT_TIME
    )
    assert repository.count(
        status=OrderStatus.CANCELLED,
    ) == 1


def test_cancel_new_order_before_submission(
    tmp_path: Path,
) -> None:
    """未送信のNEW注文をBrokerへ送らず取消する。"""

    repository, broker, service = create_environment(
        tmp_path,
    )

    result = service.cancel(
        "order-001",
    )

    assert result.decision is (
        OrderBrokerSyncDecision.CANCELLED
    )
    assert result.broker_snapshot is None
    assert result.order_record is not None
    assert result.order_record.status is (
        OrderStatus.CANCELLED
    )
    assert broker.list_orders() == []
    assert repository.count(
        status=OrderStatus.CANCELLED,
    ) == 1


def test_submit_is_idempotent_after_fill(
    tmp_path: Path,
) -> None:
    """全約定済み注文の再送信で二重発注しない。"""

    repository, broker, service = create_environment(
        tmp_path,
    )

    first = service.submit(
        "order-001",
    )
    second = service.submit(
        "order-001",
    )

    assert first.order_record is not None
    assert second.order_record is not None

    assert second.decision is (
        OrderBrokerSyncDecision.UNCHANGED
    )
    assert second.order_record.status is (
        OrderStatus.FILLED
    )

    assert len(broker.list_orders()) == 1
    assert broker.list_positions()[0].quantity == 100
    assert repository.count() == 1


def test_refresh_rejects_order_without_broker_id(
    tmp_path: Path,
) -> None:
    """未送信注文のBroker照会を拒否する。"""

    _repository, _broker, service = create_environment(
        tmp_path,
    )

    with pytest.raises(
        OrderBrokerConsistencyError,
        match="Broker注文ID",
    ):
        service.refresh(
            "order-001",
        )


def test_cancel_rejects_terminal_order(
    tmp_path: Path,
) -> None:
    """全約定済み注文の取消を拒否する。"""

    _repository, _broker, service = create_environment(
        tmp_path,
    )

    service.submit(
        "order-001",
    )

    with pytest.raises(
        OrderBrokerStatusError,
        match="終了済み",
    ):
        service.cancel(
            "order-001",
        )


class InvalidIdentityBroker:
    """不一致Snapshotを返すBroker。"""

    @property
    def broker_name(self) -> str:
        """Broker名を返す。"""

        return "invalid"

    def submit_order(
        self,
        order: TradeOrder,
    ) -> BrokerOrderSnapshot:
        """異なるクライアント注文IDを返す。"""

        return BrokerOrderSnapshot(
            broker_order_id="broker-001",
            client_order_id="different-order",
            code=order.code,
            side=order.side,
            status=OrderStatus.SENT,
            quantity=order.quantity,
            filled_quantity=0,
            average_fill_price=None,
            submitted_at=CURRENT_TIME,
            updated_at=CURRENT_TIME,
        )

    def cancel_order(
        self,
        broker_order_id: str,
    ) -> BrokerOrderSnapshot:
        """未使用。"""

        raise NotImplementedError(
            broker_order_id
        )

    def get_order(
        self,
        broker_order_id: str,
    ) -> BrokerOrderSnapshot:
        """未使用。"""

        raise NotImplementedError(
            broker_order_id
        )

    def list_orders(
        self,
        *,
        active_only: bool = False,
    ) -> list[BrokerOrderSnapshot]:
        """空一覧を返す。"""

        del active_only

        return []

    def list_positions(
        self,
    ):
        """空一覧を返す。"""

        return []

    def get_account(
        self,
    ):
        """未使用。"""

        raise NotImplementedError


def test_submit_rejects_broker_identity_mismatch(
    tmp_path: Path,
) -> None:
    """Brokerの注文識別情報不一致を拒否する。"""

    database_path = tmp_path / "katana.db"

    initialize_database(
        database_path,
    )

    SignalRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    ).save(
        create_signal(),
    )

    repository = OrderRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    )

    repository.create(
        create_order(),
    )

    service = OrderBrokerSyncService(
        order_repository=repository,
        broker=InvalidIdentityBroker(),
    )

    with pytest.raises(
        OrderBrokerConsistencyError,
        match="クライアント注文ID",
    ):
        service.submit(
            "order-001",
        )


class FailingBroker:
    """注文送信に失敗するBroker。"""

    @property
    def broker_name(self) -> str:
        """Broker名を返す。"""

        return "failing"

    def submit_order(
        self,
        order: TradeOrder,
    ) -> BrokerOrderSnapshot:
        """送信エラーを発生させる。"""

        raise RuntimeError(
            f"submit failed: {order.order_id}"
        )

    def cancel_order(
        self,
        broker_order_id: str,
    ) -> BrokerOrderSnapshot:
        """未使用。"""

        raise NotImplementedError(
            broker_order_id
        )

    def get_order(
        self,
        broker_order_id: str,
    ) -> BrokerOrderSnapshot:
        """未使用。"""

        raise NotImplementedError(
            broker_order_id
        )

    def list_orders(
        self,
        *,
        active_only: bool = False,
    ) -> list[BrokerOrderSnapshot]:
        """空一覧を返す。"""

        del active_only

        return []

    def list_positions(
        self,
    ):
        """空一覧を返す。"""

        return []

    def get_account(
        self,
    ):
        """未使用。"""

        raise NotImplementedError


def test_submit_failure_marks_local_order_failed(
    tmp_path: Path,
) -> None:
    """Broker送信失敗をローカルFAILEDへ保存する。"""

    database_path = tmp_path / "katana.db"

    initialize_database(
        database_path,
    )

    SignalRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    ).save(
        create_signal(),
    )

    repository = OrderRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    )

    repository.create(
        create_order(),
    )

    service = OrderBrokerSyncService(
        order_repository=repository,
        broker=FailingBroker(),
    )

    with pytest.raises(
        RuntimeError,
        match="submit failed",
    ):
        service.submit(
            "order-001",
        )

    failed = repository.get(
        "order-001",
    )

    assert failed.status is OrderStatus.FAILED
    assert failed.error_message is not None
    assert "submit failed" in failed.error_message


def test_submit_records_failure_when_continuation_enabled(
    tmp_path: Path,
) -> None:
    """continue_on_error有効時は失敗結果を返す。"""

    database_path = tmp_path / "katana.db"

    initialize_database(
        database_path,
    )

    SignalRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    ).save(
        create_signal(),
    )

    repository = OrderRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    )

    repository.create(
        create_order(),
    )

    service = OrderBrokerSyncService(
        order_repository=repository,
        broker=FailingBroker(),
    )

    result = service.submit(
        "order-001",
        continue_on_error=True,
    )

    assert result.decision is (
        OrderBrokerSyncDecision.FAILED
    )
    assert result.is_failed is True
    assert "submit failed" in (
        result.message or ""
    )