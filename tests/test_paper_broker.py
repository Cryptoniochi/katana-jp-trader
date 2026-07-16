"""Paper Brokerの注文・約定・資金・ポジション管理テスト。"""

from datetime import datetime, timezone

import pytest

from app.trading.broker_adapter import (
    BrokerAdapter,
    BrokerOrderNotFoundError,
    BrokerOrderRejectedError,
    BrokerPositionSide,
    BrokerRequestError,
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
    16,
    0,
    30,
    tzinfo=timezone.utc,
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
    """標準的なテスト注文を作成する。"""

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


def create_broker(
    *,
    initial_cash: float = 1_000_000.0,
    commission_per_order: float = 0.0,
    slippage_rate: float = 0.0,
    price: float = 2500.0,
) -> PaperBroker:
    """固定価格を返すPaper Brokerを作成する。"""

    return PaperBroker(
        settings=PaperBrokerSettings(
            initial_cash=initial_cash,
            commission_per_order=(
                commission_per_order
            ),
            slippage_rate=slippage_rate,
        ),
        price_provider=lambda _code: price,
        now_provider=lambda: CURRENT_TIME,
    )


def test_paper_broker_implements_protocol() -> None:
    """PaperBrokerがBrokerAdapterを実装する。"""

    broker = create_broker()

    assert isinstance(
        broker,
        BrokerAdapter,
    )
    assert broker.broker_name == "paper"


def test_market_buy_order_is_filled_immediately() -> None:
    """成行買い注文を即時全約定する。"""

    broker = create_broker()

    snapshot = broker.submit_order(
        create_order(),
    )

    assert snapshot.broker_order_id == (
        "paper-order-00000001"
    )
    assert snapshot.client_order_id == (
        "order-001"
    )
    assert snapshot.status is OrderStatus.FILLED
    assert snapshot.filled_quantity == 100
    assert snapshot.remaining_quantity == 0
    assert snapshot.average_fill_price == pytest.approx(
        2500.0
    )
    assert snapshot.is_terminal is True


def test_market_buy_reduces_cash_and_creates_position() -> None:
    """買い約定で現金を減らしポジションを作成する。"""

    broker = create_broker(
        initial_cash=1_000_000.0,
    )

    broker.submit_order(
        create_order(),
    )

    account = broker.get_account()
    positions = broker.list_positions()

    assert account.cash_balance == pytest.approx(
        750_000.0
    )
    assert account.buying_power == pytest.approx(
        750_000.0
    )
    assert account.market_value == pytest.approx(
        250_000.0
    )
    assert account.equity == pytest.approx(
        1_000_000.0
    )

    assert len(positions) == 1

    position = positions[0]

    assert position.code == "7203"
    assert position.side is (
        BrokerPositionSide.LONG
    )
    assert position.quantity == 100
    assert position.average_price == pytest.approx(
        2500.0
    )
    assert position.market_price == pytest.approx(
        2500.0
    )


def test_multiple_buys_use_weighted_average_price() -> None:
    """買い増し時に平均取得価格を加重平均する。"""

    prices = iter(
        [
            2500.0,
            2600.0,
        ]
    )

    broker = PaperBroker(
        settings=PaperBrokerSettings(
            initial_cash=2_000_000.0,
        ),
        price_provider=lambda _code: next(
            prices
        ),
        now_provider=lambda: CURRENT_TIME,
    )

    broker.submit_order(
        create_order(
            order_id="order-001",
            signal_id="signal-001",
            quantity=100,
        )
    )

    broker.submit_order(
        create_order(
            order_id="order-002",
            signal_id="signal-002",
            quantity=100,
        )
    )

    position = broker.list_positions()[0]

    assert position.quantity == 200
    assert position.average_price == pytest.approx(
        2550.0
    )
    assert position.market_price == pytest.approx(
        2600.0
    )


def test_market_sell_reduces_position_and_adds_cash() -> None:
    """売り注文で買いポジションを減らし現金を増やす。"""

    prices = iter(
        [
            2500.0,
            2600.0,
        ]
    )

    broker = PaperBroker(
        settings=PaperBrokerSettings(
            initial_cash=1_000_000.0,
        ),
        price_provider=lambda _code: next(
            prices
        ),
        now_provider=lambda: CURRENT_TIME,
    )

    broker.submit_order(
        create_order(
            order_id="buy-order",
            signal_id="buy-signal",
            side=OrderSide.BUY,
            quantity=100,
        )
    )

    sell_snapshot = broker.submit_order(
        create_order(
            order_id="sell-order",
            signal_id="sell-signal",
            side=OrderSide.SELL,
            quantity=40,
        )
    )

    assert sell_snapshot.status is (
        OrderStatus.FILLED
    )
    assert sell_snapshot.average_fill_price == pytest.approx(
        2600.0
    )

    position = broker.list_positions()[0]
    account = broker.get_account()

    assert position.quantity == 60
    assert position.average_price == pytest.approx(
        2500.0
    )
    assert account.cash_balance == pytest.approx(
        854_000.0
    )


def test_full_sell_closes_position() -> None:
    """全数量の売却でポジションを削除する。"""

    broker = create_broker()

    broker.submit_order(
        create_order(
            order_id="buy-order",
            signal_id="buy-signal",
            side=OrderSide.BUY,
        )
    )

    broker.submit_order(
        create_order(
            order_id="sell-order",
            signal_id="sell-signal",
            side=OrderSide.SELL,
        )
    )

    assert broker.list_positions() == []


def test_sell_without_position_is_rejected() -> None:
    """保有数量がない売り注文を拒否する。"""

    broker = create_broker()

    with pytest.raises(
        BrokerOrderRejectedError,
        match="売却可能数量",
    ):
        broker.submit_order(
            create_order(
                side=OrderSide.SELL,
            )
        )

    assert broker.list_orders() == []


def test_buy_without_buying_power_is_rejected() -> None:
    """買付余力を超える注文を拒否する。"""

    broker = create_broker(
        initial_cash=100_000.0,
    )

    with pytest.raises(
        BrokerOrderRejectedError,
        match="買付余力",
    ):
        broker.submit_order(
            create_order(
                quantity=100,
            )
        )

    assert broker.list_orders() == []
    assert broker.get_account().cash_balance == pytest.approx(
        100_000.0
    )


def test_commission_is_applied_to_cash() -> None:
    """注文手数料を現金残高へ反映する。"""

    broker = create_broker(
        initial_cash=1_000_000.0,
        commission_per_order=500.0,
    )

    broker.submit_order(
        create_order(),
    )

    assert broker.get_account().cash_balance == pytest.approx(
        749_500.0
    )


def test_buy_slippage_increases_fill_price() -> None:
    """買い注文ではスリッページ分だけ約定価格を上げる。"""

    broker = create_broker(
        slippage_rate=0.001,
    )

    snapshot = broker.submit_order(
        create_order(),
    )

    assert snapshot.average_fill_price == pytest.approx(
        2502.5
    )


def test_sell_slippage_decreases_fill_price() -> None:
    """売り注文ではスリッページ分だけ約定価格を下げる。"""

    broker = create_broker(
        initial_cash=1_000_000.0,
        slippage_rate=0.001,
    )

    broker.submit_order(
        create_order(
            order_id="buy-order",
            signal_id="buy-signal",
            side=OrderSide.BUY,
        )
    )

    snapshot = broker.submit_order(
        create_order(
            order_id="sell-order",
            signal_id="sell-signal",
            side=OrderSide.SELL,
        )
    )

    assert snapshot.average_fill_price == pytest.approx(
        2497.5
    )


def test_duplicate_client_order_returns_existing_order() -> None:
    """同じクライアント注文IDの再送信を冪等に処理する。"""

    broker = create_broker()
    order = create_order()

    first = broker.submit_order(
        order
    )
    second = broker.submit_order(
        order
    )

    assert first == second
    assert len(
        broker.list_orders()
    ) == 1
    assert broker.list_positions()[0].quantity == 100


def test_get_order_returns_saved_snapshot() -> None:
    """Broker注文IDで注文状態を取得する。"""

    broker = create_broker()

    created = broker.submit_order(
        create_order()
    )

    loaded = broker.get_order(
        created.broker_order_id
    )

    assert loaded == created


def test_get_order_rejects_missing_order() -> None:
    """存在しないBroker注文IDを拒否する。"""

    broker = create_broker()

    with pytest.raises(
        BrokerOrderNotFoundError,
        match="存在しません",
    ):
        broker.get_order(
            "missing-order"
        )


def test_completed_order_cannot_be_cancelled() -> None:
    """即時約定済み注文の取消を拒否する。"""

    broker = create_broker()

    snapshot = broker.submit_order(
        create_order()
    )

    with pytest.raises(
        BrokerRequestError,
        match="終了済み",
    ):
        broker.cancel_order(
            snapshot.broker_order_id
        )


def test_list_orders_can_filter_active_only() -> None:
    """終了済み注文をactive_only一覧から除外する。"""

    broker = create_broker()

    broker.submit_order(
        create_order()
    )

    assert len(
        broker.list_orders()
    ) == 1
    assert broker.list_orders(
        active_only=True
    ) == []


def test_limit_order_is_not_supported_yet() -> None:
    """未実装の指値注文を明示的に拒否する。"""

    broker = create_broker()

    with pytest.raises(
        BrokerRequestError,
        match="成行注文だけ",
    ):
        broker.submit_order(
            create_order(
                order_type=OrderType.LIMIT,
                limit_price=2490.0,
            )
        )


def test_price_provider_failure_is_wrapped() -> None:
    """価格取得失敗をBrokerRequestErrorへ変換する。"""

    broker = PaperBroker(
        price_provider=lambda _code: (
            (_ for _ in ()).throw(
                RuntimeError(
                    "price unavailable"
                )
            )
        ),
        now_provider=lambda: CURRENT_TIME,
    )

    with pytest.raises(
        BrokerRequestError,
        match="現在価格",
    ):
        broker.submit_order(
            create_order()
        )


def test_update_market_price_updates_unrealized_profit() -> None:
    """現在価格更新を口座評価額と含み損益へ反映する。"""

    broker = create_broker()

    broker.submit_order(
        create_order()
    )

    broker.update_market_price(
        "7203",
        2600.0,
    )

    position = broker.list_positions()[0]
    account = broker.get_account()

    assert position.market_price == pytest.approx(
        2600.0
    )
    assert position.unrealized_profit_loss == pytest.approx(
        10_000.0
    )
    assert account.market_value == pytest.approx(
        260_000.0
    )
    assert account.equity == pytest.approx(
        1_010_000.0
    )


@pytest.mark.parametrize(
    (
        "arguments",
        "message",
    ),
    [
        (
            {
                "initial_cash": -1,
            },
            "初期資金",
        ),
        (
            {
                "commission_per_order": -1,
            },
            "注文手数料",
        ),
        (
            {
                "slippage_rate": -0.1,
            },
            "スリッページ率",
        ),
        (
            {
                "currency": "JP",
            },
            "英字3文字",
        ),
        (
            {
                "broker_name": " ",
            },
            "Broker名",
        ),
    ],
)
def test_settings_reject_invalid_values(
    arguments: dict[str, object],
    message: str,
) -> None:
    """不正なPaper Broker設定を拒否する。"""

    with pytest.raises(
        ValueError,
        match=message,
    ):
        PaperBrokerSettings(
            **arguments
        )


def test_naive_current_time_is_rejected() -> None:
    """タイムゾーンなし現在日時を拒否する。"""

    broker = PaperBroker(
        price_provider=lambda _code: 2500.0,
        now_provider=lambda: datetime(
            2026,
            7,
            16,
            9,
            30,
        ),
    )

    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        broker.submit_order(
            create_order()
        )