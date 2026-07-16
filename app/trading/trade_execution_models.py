"""約定履歴の共通データモデル。"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.trading.order_models import OrderSide


@dataclass(frozen=True, slots=True)
class TradeExecution:
    """Brokerで成立した1件の約定事実。"""

    execution_id: str
    signal_id: str
    order_id: str
    broker_order_id: str
    code: str
    side: OrderSide
    quantity: int
    execution_price: float
    executed_at: datetime
    broker_name: str
    commission: float = 0.0
    slippage: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """約定内容を検証して文字列を正規化する。"""

        values = {
            "約定ID": self.execution_id.strip(),
            "シグナルID": self.signal_id.strip(),
            "注文ID": self.order_id.strip(),
            "Broker注文ID": self.broker_order_id.strip(),
            "銘柄コード": self.code.strip(),
            "Broker名": self.broker_name.strip(),
        }

        for name, value in values.items():
            if not value:
                raise ValueError(f"{name}を指定してください。")

        code = values["銘柄コード"]

        if not code.isdigit():
            raise ValueError("銘柄コードは数字で指定してください。")

        if len(code) not in {4, 5}:
            raise ValueError(
                "銘柄コードは4桁または5桁で指定してください。"
            )

        if self.quantity <= 0:
            raise ValueError("約定数量は0より大きい必要があります。")

        if self.execution_price <= 0:
            raise ValueError("約定価格は0より大きい必要があります。")

        if self.executed_at.tzinfo is None:
            raise ValueError("約定日時にはタイムゾーンが必要です。")

        if self.commission < 0:
            raise ValueError("手数料は0以上である必要があります。")

        if self.slippage < 0:
            raise ValueError("スリッページは0以上である必要があります。")

        if not isinstance(self.metadata, dict):
            raise TypeError("メタデータは辞書形式で指定してください。")

        object.__setattr__(self, "execution_id", values["約定ID"])
        object.__setattr__(self, "signal_id", values["シグナルID"])
        object.__setattr__(self, "order_id", values["注文ID"])
        object.__setattr__(
            self,
            "broker_order_id",
            values["Broker注文ID"],
        )
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "broker_name", values["Broker名"])
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def gross_value(self) -> float:
        """手数料等を含まない約定金額を返す。"""

        return self.execution_price * self.quantity

    @property
    def total_cost(self) -> float:
        """手数料・スリッページ合計を返す。"""

        return self.commission + self.slippage


@dataclass(frozen=True, slots=True)
class TradeExecutionRecord:
    """SQLiteへ保存された約定履歴。"""

    id: int
    execution: TradeExecution
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """保存済み約定履歴の整合性を検証する。"""

        if self.id <= 0:
            raise ValueError("保存IDは0より大きい必要があります。")

        if self.created_at.tzinfo is None:
            raise ValueError("作成日時にはタイムゾーンが必要です。")

        if self.updated_at.tzinfo is None:
            raise ValueError("更新日時にはタイムゾーンが必要です。")

        if self.updated_at < self.created_at:
            raise ValueError(
                "更新日時は作成日時以後である必要があります。"
            )

    @property
    def execution_id(self) -> str:
        return self.execution.execution_id

    @property
    def signal_id(self) -> str:
        return self.execution.signal_id

    @property
    def order_id(self) -> str:
        return self.execution.order_id

    @property
    def code(self) -> str:
        return self.execution.code
