"""Broker Adapter共通モデルとProtocolのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.trading.broker_adapter import (
    BrokerAccountSnapshot,
    BrokerAdapter,
    BrokerOrderSnapshot,
    BrokerPosition,
    BrokerPositionSide,
)
from app.trading.order_models import (
    OrderSide,
    OrderStatus,
    OrderType,
    TradeOrder,
)


BASE_TIME = datetime(
    2026,
    7,
    16,
    0,
    30,
    tzinfo=timezone.utc,
)


def create_order_snapshot(
    *,
    status: OrderStatus = OrderStatus.SENT,
    quantity: int = 100,
    filled_quantity: int = 0,
    average_fill_price: float | None = None,
) -> BrokerOrderSnapshot:
    """標準的なBroker注文状態を作成する。"""

    return BrokerOrderSnapshot(
        broker_order_id="broker-order-001",
        client_order_id="order-001",
        code="7203",
        side=OrderSide.BUY,
        status=status,
        quantity=quantity,
        filled_quantity=filled_quantity,
        average_fill_price=average_fill_price,
        submitted_at=BASE_TIME,
        updated_at=(
            BASE_TIME
            + timedelta(seconds=1)
        ),
        status_reason=None,
    )


def test_order_snapshot_returns_remaining_quantity() -> None:
    """未約定数量を返す。"""

    snapshot = create_order_snapshot(
        status=OrderStatus.PARTIALLY_FILLED,
        quantity=100,
        filled_quantity=40,
        average_fill_price=2500.0,
    )

    assert snapshot.remaining_quantity == 60
    assert snapshot.is_terminal is False


def test_order_snapshot_identifies_terminal_status() -> None:
    """終了状態を判定する。"""

    snapshot = create_order_snapshot(
        status=OrderStatus.FILLED,
        quantity=100,
        filled_quantity=100,
        average_fill_price=2501.0,
    )

    assert snapshot.remaining_quantity == 0
    assert snapshot.is_terminal is True


@pytest.mark.parametrize(
    (
        "arguments",
        "message",
    ),
    [
        (
            {
                "broker_order_id": " ",
            },
            "Broker注文ID",
        ),
        (
            {
                "client_order_id": " ",
            },
            "クライアント注文ID",
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
                "filled_quantity": -1,
            },
            "約定数量",
        ),
        (
            {
                "filled_quantity": 101,
            },
            "約定数量",
        ),
        (
            {
                "average_fill_price": -1.0,
            },
            "平均約定価格",
        ),
    ],
)
def test_order_snapshot_rejects_invalid_values(
    arguments: dict[str, object],
    message: str,
) -> None:
    """不正なBroker注文状態を拒否する。"""

    base_arguments: dict[str, object] = {
        "broker_order_id": "broker-order-001",
        "client_order_id": "order-001",
        "code": "7203",
        "side": OrderSide.BUY,
        "status": OrderStatus.SENT,
        "quantity": 100,
        "filled_quantity": 0,
        "average_fill_price": None,
        "submitted_at": BASE_TIME,
        "updated_at": (
            BASE_TIME
            + timedelta(seconds=1)
        ),
    }

    base_arguments.update(
        arguments
    )

    with pytest.raises(
        (
            TypeError,
            ValueError,
        ),
        match=message,
    ):
        BrokerOrderSnapshot(
            **base_arguments
        )


def test_order_snapshot_requires_fill_price_for_fill() -> None:
    """約定数量があれば平均約定価格を要求する。"""

    with pytest.raises(
        ValueError,
        match="平均約定価格",
    ):
        create_order_snapshot(
            status=OrderStatus.PARTIALLY_FILLED,
            filled_quantity=40,
            average_fill_price=None,
        )


def test_order_snapshot_rejects_price_without_fill() -> None:
    """未約定時の平均約定価格を拒否する。"""

    with pytest.raises(
        ValueError,
        match="未約定",
    ):
        create_order_snapshot(
            status=OrderStatus.SENT,
            filled_quantity=0,
            average_fill_price=2500.0,
        )


def test_order_snapshot_rejects_naive_datetime() -> None:
    """タイムゾーンなし日時を拒否する。"""

    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        BrokerOrderSnapshot(
            broker_order_id="broker-order-001",
            client_order_id="order-001",
            code="7203",
            side=OrderSide.BUY,
            status=OrderStatus.SENT,
            quantity=100,
            filled_quantity=0,
            average_fill_price=None,
            submitted_at=datetime(
                2026,
                7,
                16,
                9,
                30,
            ),
            updated_at=BASE_TIME,
        )


def test_order_snapshot_rejects_update_before_submission() -> None:
    """送信日時より前の更新日時を拒否する。"""

    with pytest.raises(
        ValueError,
        match="送信日時以後",
    ):
        BrokerOrderSnapshot(
            broker_order_id="broker-order-001",
            client_order_id="order-001",
            code="7203",
            side=OrderSide.BUY,
            status=OrderStatus.SENT,
            quantity=100,
            filled_quantity=0,
            average_fill_price=None,
            submitted_at=BASE_TIME,
            updated_at=(
                BASE_TIME
                - timedelta(seconds=1)
            ),
        )


def test_long_position_calculates_values() -> None:
    """買いポジションの評価額と含み損益を計算する。"""

    position = BrokerPosition(
        code="7203",
        side=BrokerPositionSide.LONG,
        quantity=100,
        average_price=2500.0,
        market_price=2550.0,
        updated_at=BASE_TIME,
    )

    assert position.acquisition_value == pytest.approx(
        250_000.0
    )
    assert position.market_value == pytest.approx(
        255_000.0
    )
    assert position.unrealized_profit_loss == pytest.approx(
        5_000.0
    )


def test_short_position_reverses_profit_loss() -> None:
    """売りポジションの損益方向を反転する。"""

    position = BrokerPosition(
        code="7203",
        side=BrokerPositionSide.SHORT,
        quantity=100,
        average_price=2500.0,
        market_price=2450.0,
        updated_at=BASE_TIME,
    )

    assert position.unrealized_profit_loss == pytest.approx(
        5_000.0
    )


def test_position_without_market_price_returns_none() -> None:
    """現在価格がなければ時価と含み損益を返さない。"""

    position = BrokerPosition(
        code="7203",
        side=BrokerPositionSide.LONG,
        quantity=100,
        average_price=2500.0,
    )

    assert position.market_value is None
    assert position.unrealized_profit_loss is None


@pytest.mark.parametrize(
    (
        "arguments",
        "message",
    ),
    [
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
            "保有数量",
        ),
        (
            {
                "average_price": 0,
            },
            "平均取得価格",
        ),
        (
            {
                "market_price": -1,
            },
            "現在価格",
        ),
    ],
)
def test_position_rejects_invalid_values(
    arguments: dict[str, object],
    message: str,
) -> None:
    """不正なポジション情報を拒否する。"""

    base_arguments: dict[str, object] = {
        "code": "7203",
        "side": BrokerPositionSide.LONG,
        "quantity": 100,
        "average_price": 2500.0,
        "market_price": 2550.0,
        "updated_at": BASE_TIME,
    }

    base_arguments.update(
        arguments
    )

    with pytest.raises(
        (
            TypeError,
            ValueError,
        ),
        match=message,
    ):
        BrokerPosition(
            **base_arguments
        )


def test_account_snapshot_normalizes_currency() -> None:
    """通貨コードを大文字へ正規化する。"""

    account = BrokerAccountSnapshot(
        currency="jpy",
        cash_balance=1_000_000.0,
        buying_power=900_000.0,
        market_value=500_000.0,
        equity=1_500_000.0,
        updated_at=BASE_TIME,
    )

    assert account.currency == "JPY"


@pytest.mark.parametrize(
    (
        "arguments",
        "message",
    ),
    [
        (
            {
                "currency": "JP",
            },
            "3文字",
        ),
        (
            {
                "cash_balance": -1,
            },
            "現金残高",
        ),
        (
            {
                "buying_power": -1,
            },
            "買付余力",
        ),
        (
            {
                "market_value": -1,
            },
            "保有時価総額",
        ),
        (
            {
                "equity": -1,
            },
            "純資産額",
        ),
    ],
)
def test_account_snapshot_rejects_invalid_values(
    arguments: dict[str, object],
    message: str,
) -> None:
    """不正な口座資金情報を拒否する。"""

    base_arguments: dict[str, object] = {
        "currency": "JPY",
        "cash_balance": 1_000_000.0,
        "buying_power": 900_000.0,
        "market_value": 500_000.0,
        "equity": 1_500_000.0,
        "updated_at": BASE_TIME,
    }

    base_arguments.update(
        arguments
    )

    with pytest.raises(
        (
            TypeError,
            ValueError,
        ),
        match=message,
    ):
        BrokerAccountSnapshot(
            **base_arguments
        )


class FakeBroker:
    """BrokerAdapterを実装するテスト用Broker。"""

    @property
    def broker_name(self) -> str:
        """Broker名を返す。"""

        return "fake"

    def submit_order(
        self,
        order: TradeOrder,
    ) -> BrokerOrderSnapshot:
        """固定の送信済み状態を返す。"""

        return BrokerOrderSnapshot(
            broker_order_id="broker-order-001",
            client_order_id=order.order_id,
            code=order.code,
            side=order.side,
            status=OrderStatus.SENT,
            quantity=order.quantity,
            filled_quantity=0,
            average_fill_price=None,
            submitted_at=BASE_TIME,
            updated_at=BASE_TIME,
        )

    def cancel_order(
        self,
        broker_order_id: str,
    ) -> BrokerOrderSnapshot:
        """取消済み状態を返す。"""

        del broker_order_id

        return create_order_snapshot(
            status=OrderStatus.CANCELLED,
        )

    def get_order(
        self,
        broker_order_id: str,
    ) -> BrokerOrderSnapshot:
        """固定注文状態を返す。"""

        del broker_order_id

        return create_order_snapshot()

    def list_orders(
        self,
        *,
        active_only: bool = False,
    ) -> list[BrokerOrderSnapshot]:
        """固定注文一覧を返す。"""

        del active_only

        return [
            create_order_snapshot()
        ]

    def list_positions(
        self,
    ) -> list[BrokerPosition]:
        """空のポジション一覧を返す。"""

        return []

    def get_account(
        self,
    ) -> BrokerAccountSnapshot:
        """固定口座情報を返す。"""

        return BrokerAccountSnapshot(
            currency="JPY",
            cash_balance=1_000_000.0,
            buying_power=1_000_000.0,
            market_value=0.0,
            equity=1_000_000.0,
            updated_at=BASE_TIME,
        )


def test_runtime_protocol_accepts_complete_broker() -> None:
    """必要メソッドを持つ実装をBrokerAdapterとして認識する。"""

    broker = FakeBroker()

    assert isinstance(
        broker,
        BrokerAdapter,
    )


def test_fake_broker_can_submit_order() -> None:
    """Protocol実装を通じて注文を送信できる。"""

    broker: BrokerAdapter = FakeBroker()

    order = TradeOrder(
        order_id="order-001",
        signal_id="signal-001",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=100,
    )

    snapshot = broker.submit_order(
        order
    )

    assert snapshot.client_order_id == (
        "order-001"
    )
    assert snapshot.status is OrderStatus.SENT
    assert broker.broker_name == "fake"