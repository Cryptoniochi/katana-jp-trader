"""バックテスト結果のデータモデル。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """複数取引の集計結果。"""

    total_profit: float
    trade_count: int
    win_count: int
    loss_count: int
    breakeven_count: int

    @property
    def win_rate(self) -> float:
        """全取引に対する勝ち取引の割合を百分率で返す。"""

        if self.trade_count == 0:
            return 0.0

        return self.win_count / self.trade_count * 100

    @property
    def average_profit(self) -> float:
        """1取引あたりの平均損益を返す。"""

        if self.trade_count == 0:
            return 0.0

        return self.total_profit / self.trade_count
