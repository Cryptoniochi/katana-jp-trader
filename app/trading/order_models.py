"""証券会社へ送信する注文の共通データモデル。"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class OrderSide(StrEnum):
    """注文の売買方向。"""

    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """注文価格の指定方式。"""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(StrEnum):
    """注文のライフサイクル状態。"""

    NEW = "new"
    QUEUED = "queued"
    SENT = "sent"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        """これ以上状態遷移しない終了状態か返す。"""

        return self in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.FAILED,
        }

    @property
    def is_active(self) -> bool:
        """発注処理が継続中の状態か返す。"""

        return not self.is_terminal


@dataclass(frozen=True, slots=True)
class TradeOrder:
    """売買シグナルから作成された注文内容。"""

    order_id: str
    signal_id: str
    code: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    limit_price: float | None = None
    stop_price: float | None = None

    def __post_init__(self) -> None:
        """注文内容を検証して文字列を正規化する。"""

        normalized_order_id = self.order_id.strip()
        normalized_signal_id = self.signal_id.strip()
        normalized_code = self.code.strip()

        if not normalized_order_id:
            raise ValueError(
                "注文IDを指定してください。"
            )

        if not normalized_signal_id:
            raise ValueError(
                "シグナルIDを指定してください。"
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

        if (
            self.limit_price is not None
            and self.limit_price <= 0
        ):
            raise ValueError(
                "指値価格は0より大きい必要があります。"
            )

        if (
            self.stop_price is not None
            and self.stop_price <= 0
        ):
            raise ValueError(
                "逆指値価格は0より大きい必要があります。"
            )

        if (
            self.order_type is OrderType.MARKET
            and (
                self.limit_price is not None
                or self.stop_price is not None
            )
        ):
            raise ValueError(
                "成行注文には指値価格・逆指値価格を"
                "設定できません。"
            )

        if (
            self.order_type is OrderType.LIMIT
            and self.limit_price is None
        ):
            raise ValueError(
                "指値注文には指値価格が必要です。"
            )

        if (
            self.order_type is OrderType.LIMIT
            and self.stop_price is not None
        ):
            raise ValueError(
                "指値注文には逆指値価格を設定できません。"
            )

        if (
            self.order_type is OrderType.STOP
            and self.stop_price is None
        ):
            raise ValueError(
                "逆指値注文には逆指値価格が必要です。"
            )

        if (
            self.order_type is OrderType.STOP
            and self.limit_price is not None
        ):
            raise ValueError(
                "逆指値注文には指値価格を設定できません。"
            )

        if (
            self.order_type is OrderType.STOP_LIMIT
            and (
                self.limit_price is None
                or self.stop_price is None
            )
        ):
            raise ValueError(
                "逆指値付き指値注文には"
                "指値価格と逆指値価格が必要です。"
            )

        object.__setattr__(
            self,
            "order_id",
            normalized_order_id,
        )
        object.__setattr__(
            self,
            "signal_id",
            normalized_signal_id,
        )
        object.__setattr__(
            self,
            "code",
            normalized_code,
        )


@dataclass(frozen=True, slots=True)
class TradeOrderRecord:
    """SQLiteへ保存された注文と現在状態。"""

    id: int
    order: TradeOrder
    status: OrderStatus
    filled_quantity: int
    average_fill_price: float | None
    broker_order_id: str | None
    status_reason: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    completed_at: datetime | None

    def __post_init__(self) -> None:
        """保存済み注文の整合性を検証する。"""

        if self.id <= 0:
            raise ValueError(
                "保存IDは0より大きい必要があります。"
            )

        for name, value in {
            "作成日時": self.created_at,
            "更新日時": self.updated_at,
        }.items():
            if value.tzinfo is None:
                raise ValueError(
                    f"{name}にはタイムゾーンが必要です。"
                )

        if self.updated_at < self.created_at:
            raise ValueError(
                "更新日時は作成日時以後である必要があります。"
            )

        if (
            self.submitted_at is not None
            and self.submitted_at.tzinfo is None
        ):
            raise ValueError(
                "送信日時にはタイムゾーンが必要です。"
            )

        if (
            self.completed_at is not None
            and self.completed_at.tzinfo is None
        ):
            raise ValueError(
                "完了日時にはタイムゾーンが必要です。"
            )

        if not (
            0
            <= self.filled_quantity
            <= self.order.quantity
        ):
            raise ValueError(
                "約定数量は0以上かつ"
                "注文数量以下である必要があります。"
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
                < self.order.quantity
            )
        ):
            raise ValueError(
                "部分約定状態には注文数量未満の"
                "約定数量が必要です。"
            )

        if (
            self.status is OrderStatus.FILLED
            and self.filled_quantity
            != self.order.quantity
        ):
            raise ValueError(
                "全約定状態では約定数量と"
                "注文数量が一致する必要があります。"
            )

        if (
            self.status.is_terminal
            and self.completed_at is None
        ):
            raise ValueError(
                "終了状態には完了日時が必要です。"
            )

        if (
            not self.status.is_terminal
            and self.completed_at is not None
        ):
            raise ValueError(
                "継続中状態には完了日時を"
                "設定できません。"
            )

    @property
    def order_id(self) -> str:
        """注文IDを返す。"""

        return self.order.order_id

    @property
    def signal_id(self) -> str:
        """元シグナルIDを返す。"""

        return self.order.signal_id

    @property
    def code(self) -> str:
        """銘柄コードを返す。"""

        return self.order.code

    @property
    def remaining_quantity(self) -> int:
        """未約定数量を返す。"""

        return (
            self.order.quantity
            - self.filled_quantity
        )