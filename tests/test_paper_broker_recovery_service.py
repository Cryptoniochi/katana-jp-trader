"""PaperBrokerRecoveryServiceの再起動復元テスト。"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.trading.broker_adapter import (
    BrokerPositionSide,
)
from app.trading.order_models import (
    OrderSide,
    OrderStatus,
    OrderType,
    TradeOrder,
)
from app.trading.paper_broker import (
    PaperBroker,
    PaperBrokerSettings,
)
from app.trading.paper_broker_recovery_service import (
    PaperBrokerRecoveryError,
    PaperBrokerRecoveryService,
)
from app.trading.portfolio_models import (
    PortfolioPositionSnapshot,
    PortfolioSnapshot,
)
from app.trading.position_models import (
    TradingPosition,
    TradingPositionRecord,
)


CURRENT_TIME = datetime(
    2026,
    7,
    19,
    1,
    0,
    tzinfo=timezone.utc,
)


class FakeOrderRepository:
    """固定注文一覧を返すRepository。"""

    def __init__(
        self,
        records: list[object],
    ) -> None:
        self.records = records

    def list_recent(
        self,
        *,
        limit: int = 100,
        code=None,
        status=None,
        side=None,
    ) -> list[object]:
        return list(
            self.records[:limit]
        )


class FakePositionRepository:
    """固定ポジション一覧を返すRepository。"""

    def __init__(
        self,
        records: list[TradingPositionRecord],
    ) -> None:
        self.records = records

    def list_recent(
        self,
        *,
        limit: int = 100,
        code=None,
        side=None,
    ) -> list[TradingPositionRecord]:
        return list(
            self.records[:limit]
        )


class FakePortfolioRepository:
    """固定Portfolioを返すRepository。"""

    def __init__(
        self,
        snapshot: PortfolioSnapshot | None,
    ) -> None:
        self.snapshot = snapshot

    def latest(
        self,
    ) -> PortfolioSnapshot | None:
        return self.snapshot


class FailingOrderRepository:
    """読込時に失敗するRepository。"""

    def list_recent(
        self,
        *,
        limit: int = 100,
        code=None,
        status=None,
        side=None,
    ) -> list[object]:
        raise RuntimeError(
            "database unavailable"
        )


def create_broker(
    *,
    initial_cash: float = 1_000_000.0,
    market_price: float = 2600.0,
) -> PaperBroker:
    """固定価格・固定時計のPaperBrokerを作成する。"""

    return PaperBroker(
        price_provider=lambda _code: market_price,
        settings=PaperBrokerSettings(
            initial_cash=initial_cash,
        ),
        now_provider=lambda: CURRENT_TIME,
    )


def create_position_record(
) -> TradingPositionRecord:
    """復元対象のローカルポジションを作成する。"""

    return TradingPositionRecord(
        id=1,
        position=TradingPosition(
            position_id="position-7203-long",
            code="7203",
            side=BrokerPositionSide.LONG,
            quantity=100,
            average_cost=2500.0,
            realized_profit_loss=0.0,
            opened_at=CURRENT_TIME,
        ),
        created_at=CURRENT_TIME,
        updated_at=CURRENT_TIME,
    )


def create_portfolio_snapshot(
) -> PortfolioSnapshot:
    """復元対象のPortfolio Snapshotを作成する。"""

    return PortfolioSnapshot(
        currency="JPY",
        cash_balance=750_000.0,
        buying_power=750_000.0,
        broker_market_value=260_000.0,
        broker_equity=1_010_000.0,
        positions=(
            PortfolioPositionSnapshot(
                position_id="position-7203-long",
                code="7203",
                side=BrokerPositionSide.LONG,
                quantity=100,
                average_cost=2500.0,
                market_price=2600.0,
                realized_profit_loss=0.0,
            ),
        ),
        generated_at=CURRENT_TIME,
    )


def create_pending_order(
) -> TradeOrder:
    """復元対象の未約定注文を作成する。"""

    return TradeOrder(
        order_id="order-pending",
        signal_id="signal-pending",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=2400.0,
    )


def create_order_record(
) -> object:
    """Recovery Serviceが読む保存済み注文Recordを作成する。"""

    order = create_pending_order()

    return SimpleNamespace(
        order=order,
        broker_order_id="paper-order-00000007",
        status=OrderStatus.SENT,
        filled_quantity=0,
        average_fill_price=None,
        submitted_at=CURRENT_TIME,
        created_at=CURRENT_TIME,
        updated_at=CURRENT_TIME,
        status_reason="waiting for limit price",
    )


def create_service(
    *,
    broker: PaperBroker,
    order_records: list[object] | None = None,
    position_records: (
        list[TradingPositionRecord] | None
    ) = None,
    portfolio_snapshot: (
        PortfolioSnapshot | None
    ) = None,
) -> PaperBrokerRecoveryService:
    """標準的なRecovery Serviceを作成する。"""

    return PaperBrokerRecoveryService(
        broker=broker,
        order_repository=FakeOrderRepository(
            order_records or []
        ),
        position_repository=FakePositionRepository(
            position_records or []
        ),
        portfolio_repository=FakePortfolioRepository(
            portfolio_snapshot
        ),
    )


def test_recover_restores_cash_position_order_and_price(
) -> None:
    """現金・ポジション・注文・現在価格を一括復元する。"""

    broker = create_broker()

    result = create_service(
        broker=broker,
        order_records=[
            create_order_record(),
        ],
        position_records=[
            create_position_record(),
        ],
        portfolio_snapshot=(
            create_portfolio_snapshot()
        ),
    ).recover()

    account = broker.get_account()
    positions = broker.list_positions()
    active_orders = broker.list_orders(
        active_only=True
    )

    assert result.restored is True
    assert result.used_portfolio_snapshot is True
    assert result.cash_balance == pytest.approx(
        750_000.0
    )
    assert result.position_count == 1
    assert result.order_count == 1
    assert result.market_price_count == 1

    assert account.cash_balance == pytest.approx(
        750_000.0
    )
    assert account.market_value == pytest.approx(
        260_000.0
    )
    assert account.equity == pytest.approx(
        1_010_000.0
    )

    assert len(positions) == 1
    assert positions[0].code == "7203"
    assert positions[0].quantity == 100
    assert positions[0].average_price == pytest.approx(
        2500.0
    )
    assert positions[0].market_price == pytest.approx(
        2600.0
    )

    assert len(active_orders) == 1
    assert active_orders[0].broker_order_id == (
        "paper-order-00000007"
    )
    assert active_orders[0].client_order_id == (
        "order-pending"
    )
    assert broker.get_market_price(
        "7203"
    ) == pytest.approx(2600.0)


def test_recover_continues_broker_order_sequence(
) -> None:
    """復元済み最大Broker注文IDの次から採番する。"""

    broker = create_broker()

    create_service(
        broker=broker,
        order_records=[
            create_order_record(),
        ],
    ).recover()

    submitted = broker.submit_order(
        TradeOrder(
            order_id="order-next",
            signal_id="signal-next",
            code="7203",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            limit_price=2400.0,
        )
    )

    assert submitted.broker_order_id == (
        "paper-order-00000008"
    )


def test_recover_uses_initial_cash_without_portfolio(
) -> None:
    """初回起動では設定された初期資金を使用する。"""

    broker = create_broker(
        initial_cash=2_000_000.0,
    )

    result = create_service(
        broker=broker,
    ).recover()

    assert result.used_portfolio_snapshot is False
    assert result.is_empty is True
    assert result.cash_balance == pytest.approx(
        2_000_000.0
    )
    assert broker.get_account().cash_balance == pytest.approx(
        2_000_000.0
    )


def test_recover_ignores_order_without_broker_order_id(
) -> None:
    """Broker未送信注文はBroker内部へ復元しない。"""

    unsent = SimpleNamespace(
        order=create_pending_order(),
        broker_order_id=None,
        status=OrderStatus.NEW,
        filled_quantity=0,
        average_fill_price=None,
        submitted_at=None,
        created_at=CURRENT_TIME,
        updated_at=CURRENT_TIME,
        status_reason=None,
    )
    broker = create_broker()

    result = create_service(
        broker=broker,
        order_records=[unsent],
    ).recover()

    assert result.order_count == 0
    assert broker.list_orders() == []


def test_recover_wraps_repository_failure(
) -> None:
    """Repository読込失敗をRecovery専用例外へ変換する。"""

    broker = create_broker()
    service = PaperBrokerRecoveryService(
        broker=broker,
        order_repository=FailingOrderRepository(),
        position_repository=FakePositionRepository(
            []
        ),
        portfolio_repository=FakePortfolioRepository(
            None
        ),
    )

    with pytest.raises(
        PaperBrokerRecoveryError,
        match="Repository",
    ):
        service.recover()


def test_recover_rejects_duplicate_positions(
) -> None:
    """同一銘柄・方向の重複ポジションを拒否する。"""

    broker = create_broker()
    duplicate = create_position_record()

    service = create_service(
        broker=broker,
        position_records=[
            create_position_record(),
            duplicate,
        ],
    )

    with pytest.raises(
        PaperBrokerRecoveryError,
        match="重複",
    ):
        service.recover()
