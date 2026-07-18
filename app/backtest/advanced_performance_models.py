"""バックテスト高度分析の共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PerformanceBreakdown:
    """任意グループ単位のトレード成績。"""

    key: str
    trade_count: int
    winning_trade_count: int
    losing_trade_count: int
    flat_trade_count: int
    gross_profit: float
    gross_loss: float
    net_profit_loss: float
    win_rate: float | None
    profit_factor: float | None
    average_profit_loss: float | None

    def __post_init__(self) -> None:
        """内訳指標を検証して正規化する。"""

        key = self.key.strip()

        if not key:
            raise ValueError(
                "Performance BreakdownのKeyを指定してください。"
            )

        counts = (
            self.trade_count,
            self.winning_trade_count,
            self.losing_trade_count,
            self.flat_trade_count,
        )

        if any(value < 0 for value in counts):
            raise ValueError(
                "トレード件数は0以上である必要があります。"
            )

        if (
            self.winning_trade_count
            + self.losing_trade_count
            + self.flat_trade_count
            != self.trade_count
        ):
            raise ValueError(
                "勝敗件数の合計がトレード件数と一致しません。"
            )

        if self.gross_profit < 0 or self.gross_loss < 0:
            raise ValueError(
                "総利益・総損失は0以上である必要があります。"
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

        object.__setattr__(self, "key", key)


@dataclass(frozen=True, slots=True)
class AdvancedPerformanceAnalytics:
    """バックテスト高度分析結果。"""

    trade_count: int
    average_trade_return: float | None
    trade_return_volatility: float | None
    trade_sharpe_ratio: float | None
    downside_deviation: float | None
    payoff_ratio: float | None
    average_holding_seconds: float | None
    maximum_holding_seconds: float | None
    monthly: tuple[PerformanceBreakdown, ...]
    by_code: tuple[PerformanceBreakdown, ...]
    by_entry_hour: tuple[PerformanceBreakdown, ...]
    by_exit_reason: tuple[PerformanceBreakdown, ...]

    def __post_init__(self) -> None:
        """高度分析結果を検証する。"""

        if self.trade_count < 0:
            raise ValueError(
                "トレード件数は0以上である必要があります。"
            )

        if (
            self.trade_return_volatility is not None
            and self.trade_return_volatility < 0
        ):
            raise ValueError(
                "リターン変動率は0以上である必要があります。"
            )

        if (
            self.downside_deviation is not None
            and self.downside_deviation < 0
        ):
            raise ValueError(
                "下方偏差は0以上である必要があります。"
            )

        if (
            self.payoff_ratio is not None
            and self.payoff_ratio < 0
        ):
            raise ValueError(
                "Payoff Ratioは0以上である必要があります。"
            )

        for name, value in {
            "平均保有秒数": self.average_holding_seconds,
            "最大保有秒数": self.maximum_holding_seconds,
        }.items():
            if value is not None and value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )
