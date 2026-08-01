"""Trade Journalを集計する戦略成績モデル。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class StrategyPerformance:
    """1戦略の集計済み成績。"""

    strategy_name: str
    trade_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    win_rate: float | None
    gross_profit: float
    gross_loss: float
    net_profit_loss: float
    profit_factor: float | None
    average_profit_loss: float | None
    average_win: float | None
    average_loss: float | None
    average_return_rate: float | None
    average_win_rate: float | None
    average_loss_rate: float | None
    expectancy: float | None
    average_holding_minutes: float | None
    maximum_drawdown: float
    maximum_drawdown_rate: float | None
    average_mfe_rate: float | None
    average_mae_rate: float | None
    score: float

    def __post_init__(self) -> None:
        if not self.strategy_name.strip():
            raise ValueError(
                "戦略名を指定してください。"
            )

        for name, value in {
            "取引数": self.trade_count,
            "勝数": self.win_count,
            "敗数": self.loss_count,
            "引分数": self.breakeven_count,
        }.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        if (
            self.win_count
            + self.loss_count
            + self.breakeven_count
            != self.trade_count
        ):
            raise ValueError(
                "勝敗件数の合計が取引数と一致しません。"
            )

        if not 0.0 <= self.score <= 100.0:
            raise ValueError(
                "スコアは0以上100以下である必要があります。"
            )

        object.__setattr__(
            self,
            "strategy_name",
            self.strategy_name.strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StrategyPerformancePayload:
    """Dashboard APIへ返す戦略成績Payload。"""

    generated_at: datetime
    period_start: datetime | None
    period_end: datetime | None
    rankings: tuple[StrategyPerformance, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "period_start": (
                self.period_start.isoformat()
                if self.period_start is not None
                else None
            ),
            "period_end": (
                self.period_end.isoformat()
                if self.period_end is not None
                else None
            ),
            "rankings": [
                item.to_dict()
                for item in self.rankings
            ],
        }
