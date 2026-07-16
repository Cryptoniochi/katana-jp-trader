"""証券会社やPaper Brokerが実装する共通インターフェース。"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from app.trading.order_models import (
    OrderSide,
    OrderStatus,
    TradeOrder,
)


class BrokerError(RuntimeError):
    """Broker Adapterで発生する例外の基底クラス。"""


class BrokerConnectionError(BrokerError):
    """証券会社またはPaper Brokerへの接続失敗。"""


class BrokerAuthenticationError(BrokerError):
    """証券会社への認証失敗。"""


class BrokerRequestError(BrokerError):
    """注文送信や照会要求の失敗。"""


class BrokerOrderNotFoundError(BrokerError):
    """指定した注文がBroker側に存在しないことを表す。"""


class BrokerOrderRejectedError(BrokerError):
    """Brokerが注文を拒否したことを表す。"""


class BrokerAccountError(BrokerError):
    """口座情報または買付余力の取得失敗。"""


class BrokerPositionSide(StrEnum):
    """Broker上の保有ポジション方向。"""

    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True, slots=True)
class BrokerOrderSnapshot:
    """Broker側に存在する注文の最新状態。"""

    broker_order_id: str
    client_order_id: str
    code: str
    side: OrderSide
    status: OrderStatus
    quantity: int
    filled_quantity: int
    average_fill_price: float | None
    submitted_at: datetime
    updated_at: datetime
    status_reason: str | None = None

    def __post_init__(self) -> None:
        """Broker注文状態の整合性を検証する。"""

        normalized_broker_order_id = (
            self.broker_order_id.strip()
        )
        normalized_client_order_id = (
            self.client_order_id.strip()
        )
        normalized_code = self.code.strip()
        normalized_status_reason = (
            self.status_reason.strip()
            if self.status_reason is not None
            else None
        )

        if not normalized_broker_order_id:
            raise ValueError(
                "Broker注文IDを指定してください。"
            )

        if not normalized_client_order_id:
            raise ValueError(
                "クライアント注文IDを指定してください。"
            )

        if not normalized_code:
            raise ValueError(
                "銘柄コードを指定してください。"
            )

        if not normalized_code.isdigit():
            raise ValueError(
                "銘柄コードは数字で指定してください。"
            )

        if len(normalized_code) not in {
            4,
            5,
        }:
            raise ValueError(
                "銘柄コードは4桁または5桁で指定してください。"
            )

        if self.quantity <= 0:
            raise ValueError(
                "注文数量は0より大きい必要があります。"
            )

        if not (
            0
            <= self.filled_quantity
            <= self.quantity
        ):
            raise ValueError(
                "約定数量は0以上かつ注文数量以下で"
                "ある必要があります。"
            )

        if (
            self.average_fill_price is not None
            and self.average_fill_price <= 0
        ):
            raise ValueError(
                "平均約定価格は0より大きい必要があります。"
            )

        if (
            self.filled_quantity == 0
            and self.average_fill_price is not None
        ):
            raise ValueError(
                "未約定注文には平均約定価格を"
                "設定できません。"
            )

        if (
            self.filled_quantity > 0
            and self.average_fill_price is None
        ):
            raise ValueError(
                "約定済み注文には平均約定価格が必要です。"
            )

        if (
            self.status is OrderStatus.PARTIALLY_FILLED
            and not (
                0
                < self.filled_quantity
                < self.quantity
            )
        ):
            raise ValueError(
                "部分約定状態には注文数量未満の"
                "約定数量が必要です。"
            )

        if (
            self.status is OrderStatus.FILLED
            and self.filled_quantity != self.quantity
        ):
            raise ValueError(
                "全約定状態では約定数量と"
                "注文数量が一致する必要があります。"
            )

        if self.submitted_at.tzinfo is None:
            raise ValueError(
                "注文送信日時にはタイムゾーンが必要です。"
            )

        if self.updated_at.tzinfo is None:
            raise ValueError(
                "注文更新日時にはタイムゾーンが必要です。"
            )

        if self.updated_at < self.submitted_at:
            raise ValueError(
                "注文更新日時は送信日時以後である必要があります。"
            )

        if normalized_status_reason == "":
            normalized_status_reason = None

        object.__setattr__(
            self,
            "broker_order_id",
            normalized_broker_order_id,
        )
        object.__setattr__(
            self,
            "client_order_id",
            normalized_client_order_id,
        )
        object.__setattr__(
            self,
            "code",
            normalized_code,
        )
        object.__setattr__(
            self,
            "status_reason",
            normalized_status_reason,
        )

    @property
    def remaining_quantity(self) -> int:
        """未約定数量を返す。"""

        return (
            self.quantity
            - self.filled_quantity
        )

    @property
    def is_terminal(self) -> bool:
        """Broker注文が終了状態か返す。"""

        return self.status.is_terminal


@dataclass(frozen=True, slots=True)
class BrokerPosition:
    """Broker上の現在ポジション。"""

    code: str
    side: BrokerPositionSide
    quantity: int
    average_price: float
    market_price: float | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        """ポジション情報を検証する。"""

        normalized_code = self.code.strip()

        if not normalized_code:
            raise ValueError(
                "銘柄コードを指定してください。"
            )

        if not normalized_code.isdigit():
            raise ValueError(
                "銘柄コードは数字で指定してください。"
            )

        if len(normalized_code) not in {
            4,
            5,
        }:
            raise ValueError(
                "銘柄コードは4桁または5桁で指定してください。"
            )

        if self.quantity <= 0:
            raise ValueError(
                "保有数量は0より大きい必要があります。"
            )

        if self.average_price <= 0:
            raise ValueError(
                "平均取得価格は0より大きい必要があります。"
            )

        if (
            self.market_price is not None
            and self.market_price <= 0
        ):
            raise ValueError(
                "現在価格は0より大きい必要があります。"
            )

        if (
            self.updated_at is not None
            and self.updated_at.tzinfo is None
        ):
            raise ValueError(
                "ポジション更新日時には"
                "タイムゾーンが必要です。"
            )

        object.__setattr__(
            self,
            "code",
            normalized_code,
        )

    @property
    def market_value(self) -> float | None:
        """現在価格があれば時価評価額を返す。"""

        if self.market_price is None:
            return None

        return (
            self.market_price
            * self.quantity
        )

    @property
    def acquisition_value(self) -> float:
        """取得金額を返す。"""

        return (
            self.average_price
            * self.quantity
        )

    @property
    def unrealized_profit_loss(
        self,
    ) -> float | None:
        """現在価格があれば含み損益を返す。"""

        if self.market_price is None:
            return None

        raw_profit_loss = (
            self.market_price
            - self.average_price
        ) * self.quantity

        if self.side is BrokerPositionSide.SHORT:
            return -raw_profit_loss

        return raw_profit_loss


@dataclass(frozen=True, slots=True)
class BrokerAccountSnapshot:
    """Broker口座の資金情報。"""

    currency: str
    cash_balance: float
    buying_power: float
    market_value: float
    equity: float
    updated_at: datetime

    def __post_init__(self) -> None:
        """口座資金情報を検証する。"""

        normalized_currency = (
            self.currency.strip().upper()
        )

        if not normalized_currency:
            raise ValueError(
                "通貨コードを指定してください。"
            )

        if len(normalized_currency) != 3:
            raise ValueError(
                "通貨コードは3文字で指定してください。"
            )

        if not normalized_currency.isalpha():
            raise ValueError(
                "通貨コードは英字3文字で指定してください。"
            )

        if self.cash_balance < 0:
            raise ValueError(
                "現金残高は0以上である必要があります。"
            )

        if self.buying_power < 0:
            raise ValueError(
                "買付余力は0以上である必要があります。"
            )

        if self.market_value < 0:
            raise ValueError(
                "保有時価総額は0以上である必要があります。"
            )

        if self.equity < 0:
            raise ValueError(
                "純資産額は0以上である必要があります。"
            )

        if self.updated_at.tzinfo is None:
            raise ValueError(
                "口座更新日時にはタイムゾーンが必要です。"
            )

        object.__setattr__(
            self,
            "currency",
            normalized_currency,
        )


@runtime_checkable
class BrokerAdapter(Protocol):
    """証券会社またはPaper Brokerの共通インターフェース。"""

    @property
    def broker_name(self) -> str:
        """Brokerを識別する名前を返す。"""

    def submit_order(
        self,
        order: TradeOrder,
    ) -> BrokerOrderSnapshot:
        """注文をBrokerへ送信し、最新状態を返す。"""

    def cancel_order(
        self,
        broker_order_id: str,
    ) -> BrokerOrderSnapshot:
        """Broker注文を取り消し、最新状態を返す。"""

    def get_order(
        self,
        broker_order_id: str,
    ) -> BrokerOrderSnapshot:
        """Broker注文の最新状態を返す。"""

    def list_orders(
        self,
        *,
        active_only: bool = False,
    ) -> list[BrokerOrderSnapshot]:
        """Broker注文一覧を返す。"""

    def list_positions(
        self,
    ) -> list[BrokerPosition]:
        """Broker上の保有ポジション一覧を返す。"""

    def get_account(
        self,
    ) -> BrokerAccountSnapshot:
        """Broker口座の資金情報を返す。"""