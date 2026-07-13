"""1回の売買を表すデータモデル。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Trade:
    """買値・売値・数量・取引コストを持つ1回の取引。"""

    code: str
    buy_price: float
    sell_price: float
    quantity: int

    commission: float = 0.0
    slippage_rate: float = 0.0

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

        if self.commission < 0:
            raise ValueError("手数料は0以上である必要があります。")

        if self.slippage_rate < 0:
            raise ValueError("スリッページ率は0以上である必要があります。")

    @property
    def invested_amount(self) -> float:
        """買付金額を返す。"""

        return self.buy_price * self.quantity

    @property
    def gross_profit(self) -> float:
        """取引コスト控除前の売買損益を返す。"""

        return (self.sell_price - self.buy_price) * self.quantity

    @property
    def slippage_cost(self) -> float:
        """買い・売りの往復スリッページ費用を返す。"""

        buy_slippage = self.buy_price * self.quantity * self.slippage_rate

        sell_slippage = self.sell_price * self.quantity * self.slippage_rate

        return buy_slippage + sell_slippage

    @property
    def total_cost(self) -> float:
        """手数料とスリッページの合計を返す。"""

        return self.commission + self.slippage_cost

    @property
    def profit(self) -> float:
        """取引コスト控除後の純損益を返す。"""

        return self.gross_profit - self.total_cost

    @property
    def return_rate(self) -> float:
        """投下金額に対する純収益率を百分率で返す。"""

        return self.profit / self.invested_amount * 100
