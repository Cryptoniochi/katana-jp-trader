"""ポートフォリオ集計の共通データモデル。"""

from dataclasses import dataclass
from datetime import datetime

from app.trading.broker_adapter import BrokerPositionSide


@dataclass(frozen=True, slots=True)
class PortfolioPositionSnapshot:
    """1つの現在ポジションの評価結果。"""

    position_id: str
    code: str
    side: BrokerPositionSide
    quantity: int
    average_cost: float
    market_price: float
    realized_profit_loss: float

    def __post_init__(self) -> None:
        """評価結果を検証して文字列を正規化する。"""

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

        if self.market_price <= 0:
            raise ValueError(
                "現在価格は0より大きい必要があります。"
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

    @property
    def market_value(self) -> float:
        """現在評価額を返す。"""

        return self.market_price * self.quantity

    @property
    def unrealized_profit_loss(self) -> float:
        """含み損益を返す。"""

        raw_profit_loss = (
            self.market_price - self.average_cost
        ) * self.quantity

        if self.side is BrokerPositionSide.SHORT:
            return -raw_profit_loss

        return raw_profit_loss


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    """口座・現在ポジションを集約したポートフォリオ。"""

    currency: str
    cash_balance: float
    buying_power: float
    broker_market_value: float
    broker_equity: float
    positions: tuple[
        PortfolioPositionSnapshot,
        ...
    ]
    generated_at: datetime

    def __post_init__(self) -> None:
        """ポートフォリオ集計結果を検証する。"""

        normalized_currency = self.currency.strip().upper()

        if (
            len(normalized_currency) != 3
            or not normalized_currency.isalpha()
        ):
            raise ValueError(
                "通貨コードは英字3文字で指定してください。"
            )

        for name, value in {
            "現金残高": self.cash_balance,
            "買付余力": self.buying_power,
            "Broker評価額": self.broker_market_value,
            "Broker純資産": self.broker_equity,
        }.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        if self.generated_at.tzinfo is None:
            raise ValueError(
                "集計日時にはタイムゾーンが必要です。"
            )

        object.__setattr__(
            self,
            "currency",
            normalized_currency,
        )

    @property
    def position_count(self) -> int:
        """現在ポジション件数を返す。"""

        return len(self.positions)

    @property
    def total_acquisition_value(self) -> float:
        """取得金額合計を返す。"""

        return sum(
            position.acquisition_value
            for position in self.positions
        )

    @property
    def total_market_value(self) -> float:
        """現在評価額合計を返す。"""

        return sum(
            position.market_value
            for position in self.positions
        )

    @property
    def total_unrealized_profit_loss(self) -> float:
        """含み損益合計を返す。"""

        return sum(
            position.unrealized_profit_loss
            for position in self.positions
        )

    @property
    def total_realized_profit_loss(self) -> float:
        """実現損益合計を返す。"""

        return sum(
            position.realized_profit_loss
            for position in self.positions
        )

    @property
    def calculated_equity(self) -> float:
        """ローカル評価額を使った純資産額を返す。"""

        return self.cash_balance + self.total_market_value
