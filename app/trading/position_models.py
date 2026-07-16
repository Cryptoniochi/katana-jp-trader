"""現在保有ポジションの共通データモデル。"""

from dataclasses import dataclass
from datetime import datetime

from app.trading.broker_adapter import BrokerPositionSide


@dataclass(frozen=True, slots=True)
class TradingPosition:
    """現在保有している1つのポジション。"""

    position_id: str
    code: str
    side: BrokerPositionSide
    quantity: int
    average_cost: float
    realized_profit_loss: float
    opened_at: datetime

    def __post_init__(self) -> None:
        """ポジション内容を検証して文字列を正規化する。"""

        normalized_position_id = self.position_id.strip()
        normalized_code = self.code.strip()

        if not normalized_position_id:
            raise ValueError(
                "ポジションIDを指定してください。"
            )

        if not normalized_code:
            raise ValueError(
                "銘柄コードを指定してください。"
            )

        if not normalized_code.isdigit():
            raise ValueError(
                "銘柄コードは数字で指定してください。"
            )

        if len(normalized_code) not in {4, 5}:
            raise ValueError(
                "銘柄コードは4桁または5桁で指定してください。"
            )

        if self.quantity <= 0:
            raise ValueError(
                "保有数量は0より大きい必要があります。"
            )

        if self.average_cost <= 0:
            raise ValueError(
                "平均取得価格は0より大きい必要があります。"
            )

        if self.opened_at.tzinfo is None:
            raise ValueError(
                "ポジション開始日時にはタイムゾーンが必要です。"
            )

        object.__setattr__(
            self,
            "position_id",
            normalized_position_id,
        )
        object.__setattr__(
            self,
            "code",
            normalized_code,
        )

    @property
    def acquisition_value(self) -> float:
        """取得金額を返す。"""

        return self.average_cost * self.quantity


@dataclass(frozen=True, slots=True)
class TradingPositionRecord:
    """SQLiteへ保存された現在ポジション。"""

    id: int
    position: TradingPosition
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """保存済みポジションの整合性を検証する。"""

        if self.id <= 0:
            raise ValueError(
                "保存IDは0より大きい必要があります。"
            )

        if self.created_at.tzinfo is None:
            raise ValueError(
                "作成日時にはタイムゾーンが必要です。"
            )

        if self.updated_at.tzinfo is None:
            raise ValueError(
                "更新日時にはタイムゾーンが必要です。"
            )

        if self.updated_at < self.created_at:
            raise ValueError(
                "更新日時は作成日時以後である必要があります。"
            )

    @property
    def position_id(self) -> str:
        """ポジションIDを返す。"""

        return self.position.position_id

    @property
    def code(self) -> str:
        """銘柄コードを返す。"""

        return self.position.code

    @property
    def side(self) -> BrokerPositionSide:
        """ポジション方向を返す。"""

        return self.position.side

    @property
    def quantity(self) -> int:
        """保有数量を返す。"""

        return self.position.quantity
