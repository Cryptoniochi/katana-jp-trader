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


def test_market_buy_reduces_cash_and_creates_position() -> None:
    """買い約定で現金を減らしポジションを作成する。"""

    broker = create_broker()

    broker.submit_order(
        create_order(),
    )

    account = broker.get_account()
    positions = broker.list_positions()

    assert account.cash_balance == pytest.approx(
        750_000.0
    )
    assert account.market_value == pytest.approx(
        250_000.0
    )
    assert account.equity == pytest.approx(
        1_000_000.0
    )

    assert len(positions) == 1
    assert positions[0].quantity == 100
    assert positions[0].side is (
        BrokerPositionSide.LONG
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
        )
    )
    broker.submit_order(
        create_order(
            order_id="order-002",
            signal_id="signal-002",
        )
    )

    position = broker.list_positions()[0]

    assert position.quantity == 200
    assert position.average_price == pytest.approx(
        2550.0
    )


def test_market_sell_reduces_position_and_adds_cash() -> None:
    """売り注文で買いポジションを減らす。"""

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
        )
    )

    broker.submit_order(
        create_order(
            order_id="sell-order",
            signal_id="sell-signal",
            side=OrderSide.SELL,
            quantity=40,
        )
    )

    position = broker.list_positions()[0]

    assert position.quantity == 60
    assert broker.get_account().cash_balance == pytest.approx(
        854_000.0
    )


def test_full_sell_closes_position() -> None:
    """全数量の売却でポジションを削除する。"""

    broker = create_broker()

    broker.submit_order(
        create_order(
            order_id="buy-order",
            signal_id="buy-signal",
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
    """買付余力を超える成行注文を拒否する。"""

    broker = create_broker(
        initial_cash=100_000.0,
    )

    with pytest.raises(
        BrokerOrderRejectedError,
        match="買付余力",
    ):
        broker.submit_order(
            create_order(),
        )

    assert broker.list_orders() == []


def test_commission_is_applied_to_cash() -> None:
    """注文手数料を現金残高へ反映する。"""

    broker = create_broker(
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


def test_duplicate_client_order_returns_existing_order() -> None:
    """同じクライアント注文IDを冪等に処理する。"""

    broker = create_broker()
    order = create_order()

    first = broker.submit_order(order)
    second = broker.submit_order(order)

    assert first == second
    assert len(broker.list_orders()) == 1
    assert broker.list_positions()[0].quantity == 100


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
    """約定済み注文の取消を拒否する。"""

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


def test_buy_limit_waits_above_limit_price() -> None:
    """買い指値より市場価格が高ければ待機する。"""

    broker = create_broker(
        price=2500.0,
    )

    snapshot = broker.submit_order(
        create_order(
            order_type=OrderType.LIMIT,
            limit_price=2490.0,
        )
    )

    assert snapshot.status is OrderStatus.SENT
    assert snapshot.filled_quantity == 0
    assert broker.list_positions() == []
    assert len(
        broker.list_orders(
            active_only=True
        )
    ) == 1


def test_buy_limit_fills_when_price_falls() -> None:
    """市場価格が買い指値以下になると約定する。"""

    broker = create_broker(
        price=2500.0,
    )

    submitted = broker.submit_order(
        create_order(
            order_type=OrderType.LIMIT,
            limit_price=2490.0,
        )
    )

    changed = broker.update_market_price(
        "7203",
        2485.0,
    )

    loaded = broker.get_order(
        submitted.broker_order_id
    )

    assert len(changed) == 1
    assert loaded.status is OrderStatus.FILLED
    assert loaded.average_fill_price == pytest.approx(
        2485.0
    )
    assert broker.list_positions()[0].quantity == 100


def test_buy_limit_does_not_fill_above_limit_after_slippage() -> None:
    """買い指値はスリッページ後も指値を超えない。"""

    broker = create_broker(
        price=2500.0,
        slippage_rate=0.01,
    )

    snapshot = broker.submit_order(
        create_order(
            order_type=OrderType.LIMIT,
            limit_price=2500.0,
        )
    )

    assert snapshot.status is OrderStatus.FILLED
    assert snapshot.average_fill_price == pytest.approx(
        2500.0
    )


def test_sell_limit_fills_when_price_rises() -> None:
    """市場価格が売り指値以上になると約定する。"""

    prices = iter(
        [
            2500.0,
            2500.0,
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
        )
    )

    sell = broker.submit_order(
        create_order(
            order_id="sell-order",
            signal_id="sell-signal",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            limit_price=2550.0,
        )
    )

    assert sell.status is OrderStatus.SENT

    broker.update_market_price(
        "7203",
        2560.0,
    )

    loaded = broker.get_order(
        sell.broker_order_id
    )

    assert loaded.status is OrderStatus.FILLED
    assert loaded.average_fill_price == pytest.approx(
        2560.0
    )


def test_buy_stop_fills_when_price_rises_to_trigger() -> None:
    """買い逆指値は価格上昇で発動する。"""

    broker = create_broker(
        price=2500.0,
    )

    order = broker.submit_order(
        create_order(
            order_type=OrderType.STOP,
            stop_price=2510.0,
        )
    )

    assert order.status is OrderStatus.SENT

    broker.update_market_price(
        "7203",
        2510.0,
    )

    loaded = broker.get_order(
        order.broker_order_id
    )

    assert loaded.status is OrderStatus.FILLED
    assert loaded.average_fill_price == pytest.approx(
        2510.0
    )


def test_sell_stop_fills_when_price_falls_to_trigger() -> None:
    """売り逆指値は価格下落で発動する。"""

    prices = iter(
        [
            2500.0,
            2500.0,
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
        )
    )

    stop_order = broker.submit_order(
        create_order(
            order_id="stop-order",
            signal_id="stop-signal",
            side=OrderSide.SELL,
            order_type=OrderType.STOP,
            stop_price=2450.0,
        )
    )

    assert stop_order.status is OrderStatus.SENT

    broker.update_market_price(
        "7203",
        2440.0,
    )

    loaded = broker.get_order(
        stop_order.broker_order_id
    )

    assert loaded.status is OrderStatus.FILLED
    assert loaded.average_fill_price == pytest.approx(
        2440.0
    )


def test_stop_limit_waits_for_trigger_then_limit() -> None:
    """逆指値付き指値は発動後も指値条件まで待機する。"""

    broker = create_broker(
        price=2500.0,
    )

    order = broker.submit_order(
        create_order(
            order_type=OrderType.STOP_LIMIT,
            stop_price=2510.0,
            limit_price=2505.0,
        )
    )

    assert order.status is OrderStatus.SENT

    first_change = broker.update_market_price(
        "7203",
        2515.0,
    )

    triggered = broker.get_order(
        order.broker_order_id
    )

    assert len(first_change) == 1
    assert triggered.status is OrderStatus.SENT
    assert "stop triggered" in (
        triggered.status_reason or ""
    )

    second_change = broker.update_market_price(
        "7203",
        2505.0,
    )

    filled = broker.get_order(
        order.broker_order_id
    )

    assert len(second_change) == 1
    assert filled.status is OrderStatus.FILLED
    assert filled.average_fill_price == pytest.approx(
        2505.0
    )


def test_stop_limit_can_fill_on_trigger_tick() -> None:
    """発動時点で指値条件も満たせば即時約定する。"""

    broker = create_broker(
        price=2500.0,
    )

    order = broker.submit_order(
        create_order(
            order_type=OrderType.STOP_LIMIT,
            stop_price=2510.0,
            limit_price=2520.0,
        )
    )

    broker.update_market_price(
        "7203",
        2510.0,
    )

    loaded = broker.get_order(
        order.broker_order_id
    )

    assert loaded.status is OrderStatus.FILLED
    assert loaded.average_fill_price == pytest.approx(
        2510.0
    )


def test_waiting_order_can_be_cancelled() -> None:
    """未約定の待機注文を取り消せる。"""

    broker = create_broker(
        price=2500.0,
    )

    submitted = broker.submit_order(
        create_order(
            order_type=OrderType.LIMIT,
            limit_price=2400.0,
        )
    )

    cancelled = broker.cancel_order(
        submitted.broker_order_id
    )

    assert cancelled.status is OrderStatus.CANCELLED
    assert broker.list_orders(
        active_only=True
    ) == []

    broker.update_market_price(
        "7203",
        2300.0,
    )

    loaded = broker.get_order(
        submitted.broker_order_id
    )

    assert loaded.status is OrderStatus.CANCELLED
    assert broker.list_positions() == []


def test_price_update_only_processes_matching_code() -> None:
    """価格更新した銘柄の注文だけを処理する。"""

    broker = create_broker(
        price=2500.0,
    )

    first = broker.submit_order(
        create_order(
            order_id="order-7203",
            signal_id="signal-7203",
            code="7203",
            order_type=OrderType.LIMIT,
            limit_price=2400.0,
        )
    )

    second = broker.submit_order(
        create_order(
            order_id="order-8306",
            signal_id="signal-8306",
            code="8306",
            order_type=OrderType.LIMIT,
            limit_price=2400.0,
        )
    )

    broker.update_market_price(
        "7203",
        2350.0,
    )

    assert broker.get_order(
        first.broker_order_id
    ).status is OrderStatus.FILLED

    assert broker.get_order(
        second.broker_order_id
    ).status is OrderStatus.SENT


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

    assert position.unrealized_profit_loss == pytest.approx(
        10_000.0
    )
    assert account.market_value == pytest.approx(
        260_000.0
    )
    assert account.equity == pytest.approx(
        1_010_000.0
    )


def test_get_market_price_returns_latest_price() -> None:
    """Brokerが保持する最新価格を返す。"""

    broker = create_broker(
        price=2500.0,
    )

    broker.submit_order(
        create_order(
            order_type=OrderType.LIMIT,
            limit_price=2400.0,
        )
    )

    assert broker.get_market_price(
        "7203"
    ) == pytest.approx(
        2500.0
    )

    broker.update_market_price(
        "7203",
        2450.0,
    )

    assert broker.get_market_price(
        "7203"
    ) == pytest.approx(
        2450.0
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