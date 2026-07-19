"""Paper Broker起動時復元用の状態モデル。"""

from dataclasses import dataclass, field

from app.trading.broker_adapter import (
    BrokerOrderSnapshot,
    BrokerPosition,
)
from app.trading.order_models import TradeOrder


@dataclass(frozen=True, slots=True)
class PaperBrokerRestoredOrder:
    """復元対象となる注文とBroker側Snapshotの組。"""

    order: TradeOrder
    snapshot: BrokerOrderSnapshot

    def __post_init__(self) -> None:
        """注文とSnapshotの識別情報が一致することを検証する。"""

        mismatches: list[str] = []

        if self.snapshot.client_order_id != self.order.order_id:
            mismatches.append("client_order_id")

        if self.snapshot.code != self.order.code:
            mismatches.append("code")

        if self.snapshot.side is not self.order.side:
            mismatches.append("side")

        if self.snapshot.quantity != self.order.quantity:
            mismatches.append("quantity")

        if mismatches:
            raise ValueError(
                "復元注文とBroker Snapshotが一致しません。 "
                f"order_id={self.order.order_id} "
                f"mismatches={','.join(mismatches)}"
            )

    def as_restore_pair(
        self,
    ) -> tuple[
        TradeOrder,
        BrokerOrderSnapshot,
    ]:
        """PaperBroker.restore_state向けの組を返す。"""

        return (
            self.order,
            self.snapshot,
        )


@dataclass(frozen=True, slots=True)
class PaperBrokerState:
    """Paper Brokerへ復元する永続化済み状態。"""

    cash_balance: float
    positions: tuple[
        BrokerPosition,
        ...,
    ] = field(
        default_factory=tuple,
    )
    orders: tuple[
        PaperBrokerRestoredOrder,
        ...,
    ] = field(
        default_factory=tuple,
    )
    market_prices: dict[
        str,
        float,
    ] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        """状態全体の基本的な整合性を検証して正規化する。"""

        normalized_cash_balance = float(
            self.cash_balance
        )

        if normalized_cash_balance < 0:
            raise ValueError(
                "現金残高は0以上である必要があります。"
            )

        normalized_positions = tuple(
            self.positions
        )
        normalized_orders = tuple(
            self.orders
        )
        normalized_market_prices: dict[
            str,
            float,
        ] = {}

        position_keys: set[
            tuple[str, object]
        ] = set()

        for position in normalized_positions:
            position_key = (
                position.code,
                position.side,
            )

            if position_key in position_keys:
                raise ValueError(
                    "復元ポジションの銘柄・方向が重複しています。 "
                    f"code={position.code} "
                    f"side={position.side.value}"
                )

            position_keys.add(
                position_key
            )

        broker_order_ids: set[str] = set()
        client_order_ids: set[str] = set()

        for restored_order in normalized_orders:
            broker_order_id = (
                restored_order.snapshot.broker_order_id
            )
            client_order_id = (
                restored_order.order.order_id
            )

            if broker_order_id in broker_order_ids:
                raise ValueError(
                    "復元するBroker注文IDが重複しています。 "
                    f"broker_order_id={broker_order_id}"
                )

            if client_order_id in client_order_ids:
                raise ValueError(
                    "復元するクライアント注文IDが重複しています。 "
                    f"order_id={client_order_id}"
                )

            broker_order_ids.add(
                broker_order_id
            )
            client_order_ids.add(
                client_order_id
            )

        for code, market_price in self.market_prices.items():
            normalized_code = code.strip()
            normalized_market_price = float(
                market_price
            )

            if not normalized_code:
                raise ValueError(
                    "現在価格の銘柄コードを指定してください。"
                )

            if not normalized_code.isdigit():
                raise ValueError(
                    "現在価格の銘柄コードは数字で指定してください。 "
                    f"code={normalized_code}"
                )

            if len(normalized_code) not in {
                4,
                5,
            }:
                raise ValueError(
                    "現在価格の銘柄コードは4桁または5桁で"
                    "指定してください。 "
                    f"code={normalized_code}"
                )

            if normalized_market_price <= 0:
                raise ValueError(
                    "現在価格は0より大きい必要があります。 "
                    f"code={normalized_code} "
                    f"market_price={normalized_market_price}"
                )

            if normalized_code in normalized_market_prices:
                raise ValueError(
                    "現在価格の銘柄コードが重複しています。 "
                    f"code={normalized_code}"
                )

            normalized_market_prices[
                normalized_code
            ] = normalized_market_price

        object.__setattr__(
            self,
            "cash_balance",
            normalized_cash_balance,
        )
        object.__setattr__(
            self,
            "positions",
            normalized_positions,
        )
        object.__setattr__(
            self,
            "orders",
            normalized_orders,
        )
        object.__setattr__(
            self,
            "market_prices",
            normalized_market_prices,
        )

    @property
    def is_empty(
        self,
    ) -> bool:
        """資金以外に復元対象が存在しないか返す。"""

        return (
            not self.positions
            and not self.orders
            and not self.market_prices
        )

    def order_pairs(
        self,
    ) -> list[
        tuple[
            TradeOrder,
            BrokerOrderSnapshot,
        ]
    ]:
        """PaperBroker.restore_state向け注文一覧を返す。"""

        return [
            restored_order.as_restore_pair()
            for restored_order in self.orders
        ]

    def position_list(
        self,
    ) -> list[BrokerPosition]:
        """PaperBroker.restore_state向けポジション一覧を返す。"""

        return list(
            self.positions
        )

    def market_price_dict(
        self,
    ) -> dict[str, float]:
        """PaperBroker.restore_state向け現在価格辞書を返す。"""

        return dict(
            self.market_prices
        )
