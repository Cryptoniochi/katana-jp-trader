"""バックテスト成績指標の共通モデル。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BacktestPerformanceMetrics:
    """完結トレードから算出した成績指標。"""

    trade_count: int
    winning_trade_count: int
    losing_trade_count: int
    flat_trade_count: int
    gross_profit: float
    gross_loss: float
    net_profit_loss: float
    win_rate: float | None
    profit_factor: float | None
    average_profit: float | None
    average_loss: float | None
    expectancy: float | None
    maximum_consecutive_wins: int
    maximum_consecutive_losses: int
    unmatched_buy_quantity: int
    unmatched_sell_quantity: int

    def __post_init__(self) -> None:
        """指標の整合性を検証する。"""

        count_values = {
            "トレード件数": self.trade_count,
            "利益トレード件数": self.winning_trade_count,
            "損失トレード件数": self.losing_trade_count,
            "横ばいトレード件数": self.flat_trade_count,
            "最大連勝数": self.maximum_consecutive_wins,
            "最大連敗数": self.maximum_consecutive_losses,
            "未決済買い数量": self.unmatched_buy_quantity,
            "未対応売り数量": self.unmatched_sell_quantity,
        }

        for name, value in count_values.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        decided_count = (
            self.winning_trade_count
            + self.losing_trade_count
            + self.flat_trade_count
        )

        if decided_count != self.trade_count:
            raise ValueError(
                "勝敗件数の合計がトレード件数と一致しません。"
            )

        if self.gross_profit < 0:
            raise ValueError(
                "総利益は0以上である必要があります。"
            )

        if self.gross_loss < 0:
            raise ValueError(
                "総損失は0以上の絶対額である必要があります。"
            )

        if (
            self.win_rate is not None
            and not 0.0 <= self.win_rate <= 1.0
        ):
            raise ValueError(
                "勝率は0以上1以下である必要があります。"
            )

        if (
            self.profit_factor is not None
            and self.profit_factor < 0
        ):
            raise ValueError(
                "Profit Factorは0以上である必要があります。"
            )
