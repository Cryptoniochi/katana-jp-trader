"""1回の売買を表すデータモデル。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Trade:
    """買値・売値・数量を持つ1回の取引。"""

    code: str
    buy_price: float
    sell_price: float
    quantity: int

    def __post_init__(self) -> None:
        """不正な取引データを拒否する。"""

        if not self.code:
            raise ValueError("銘柄コードを指定してください。")

        if self.buy_price <= 0:
            raise ValueError("買値は0より大きい必要があります。")

        if self.sell_price <= 0:
            raise ValueError("売値は0より大きい必要があります。")

        if self.quantity <= 0:
            raise ValueError("数量は0より大きい必要があります。")

    @property
    def profit(self) -> float:
        """手数料を考慮しない売買損益を返す。"""

        return (self.sell_price - self.buy_price) * self.quantity

    @property
    def return_rate(self) -> float:
        """投下金額に対する収益率を百分率で返す。"""

        invested_amount = self.buy_price * self.quantity
        return self.profit / invested_amount * 100
