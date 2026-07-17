"""PaperBrokerとBrokerAdapter契約の統合テスト。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.broker.broker_health_service import (
    BrokerHealthService,
)
from app.trading.broker_adapter import (
    BrokerAdapter,
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


CURRENT_TIME = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def create_broker(
    *,
    initial_cash: float = 1_000_000.0,
    market_price: float = 2500.0,
) -> PaperBroker:
    """固定価格・固定時計のPaperBrokerを作成する。"""

    return PaperBroker(
        price_provider=lambda _code: market_price,
        settings=PaperBrokerSettings(
            initial_cash=initial_cash,
        ),
        now_provider=lambda: CURRENT_TIME,
    )


def create_order(
    *,
    order_id: str,
    side: OrderSide = OrderSide.BUY,
    order_type: OrderType = OrderType.MARKET,
    quantity: int = 100,
    limit_price: float | None = None,
) -> TradeOrder:
    """Broker契約確認用の注文を作成する。"""

    return TradeOrder(
        order_id=order_id,
        signal_id=f"signal-{order_id}",
        code="7203",
        side=side,
        order_type=order_type,
        quantity=quantity,
        limit_price=limit_price,
    )


def health_service() -> BrokerHealthService:
    """固定時計のBroker診断サービスを返す。"""

    return BrokerHealthService(
        now_provider=lambda: CURRENT_TIME
    )


def test_paper_broker_satisfies_runtime_protocol() -> None:
    """PaperBrokerがBrokerAdapter Protocolへ適合する。"""

    broker = create_broker()

    assert isinstance(broker, BrokerAdapter)


def test_paper_broker_passes_health_check_before_trading() -> None:
    """未取引状態でも実運転前診断を通過する。"""

    result = health_service().require_ready(
        create_broker()
    )

    assert result.is_healthy
    assert result.broker_name == "paper"
    assert result.active_order_count == 0
    assert result.position_count == 0


def test_market_buy_updates_order_position_and_account() -> None:
    """成行買い後の注文・保有・口座状態が整合する。"""

    broker = create_broker()
    submitted = broker.submit_order(
        create_order(order_id="order-buy")
    )

    assert submitted.status is OrderStatus.FILLED
    assert submitted.filled_quantity == 100
    assert submitted.average_fill_price == pytest.approx(
        2500.0
    )

    stored = broker.get_order(
        submitted.broker_order_id
    )
    positions = broker.list_positions()
    account = broker.get_account()

    assert stored == submitted
    assert len(positions) == 1
    assert positions[0].code == "7203"
    assert positions[0].side is BrokerPositionSide.LONG
    assert positions[0].quantity == 100
    assert positions[0].average_price == pytest.approx(
        2500.0
    )
    assert account.cash_balance == pytest.approx(
        750_000.0
    )
    assert account.market_value == pytest.approx(
        250_000.0
    )
    assert account.equity == pytest.approx(
        1_000_000.0
    )


def test_pending_limit_order_can_be_cancelled() -> None:
    """未約定の指値注文をBrokerAdapter経由で取消できる。"""

    broker = create_broker()
    submitted = broker.submit_order(
        create_order(
            order_id="order-limit",
            order_type=OrderType.LIMIT,
            limit_price=2400.0,
        )
    )

    assert submitted.status is OrderStatus.SENT
    assert len(
        broker.list_orders(active_only=True)
    ) == 1

    cancelled = broker.cancel_order(
        submitted.broker_order_id
    )

    assert cancelled.status is OrderStatus.CANCELLED
    assert cancelled.is_terminal
    assert broker.list_orders(
        active_only=True
    ) == []


def test_health_check_reflects_active_orders_and_positions() -> None:
    """診断結果に有効注文数と保有数を反映する。"""

    broker = create_broker()

    broker.submit_order(
        create_order(order_id="order-filled")
    )
    broker.submit_order(
        create_order(
            order_id="order-active",
            order_type=OrderType.LIMIT,
            limit_price=2400.0,
        )
    )

    result = health_service().check(broker)

    assert result.is_healthy
    assert result.active_order_count == 1
    assert result.position_count == 1
