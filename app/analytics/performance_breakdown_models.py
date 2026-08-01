"""Trade Journalの多角的分析モデル。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class PerformanceBreakdownRow:
    """分析軸ごとの1行。"""

    key: str
    label: str
    trade_count: int
    win_count: int
    loss_count: int
    win_rate: float | None
    net_profit_loss: float
    gross_profit: float
    gross_loss: float
    profit_factor: float | None
    average_profit_loss: float | None
    average_return_rate: float | None

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError(
                "集計キーを指定してください。"
            )

        if not self.label.strip():
            raise ValueError(
                "表示名を指定してください。"
            )

        if self.trade_count < 0:
            raise ValueError(
                "取引数は0以上である必要があります。"
            )

        if self.win_count < 0 or self.loss_count < 0:
            raise ValueError(
                "勝敗件数は0以上である必要があります。"
            )

        if self.win_count + self.loss_count > self.trade_count:
            raise ValueError(
                "勝敗件数が取引数を超えています。"
            )

        object.__setattr__(
            self,
            "key",
            self.key.strip(),
        )
        object.__setattr__(
            self,
            "label",
            self.label.strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PerformanceBreakdownPayload:
    """Dashboard APIへ返す多角的分析結果。"""

    generated_at: datetime
    weekday: tuple[PerformanceBreakdownRow, ...]
    entry_hour: tuple[PerformanceBreakdownRow, ...]
    symbol: tuple[PerformanceBreakdownRow, ...]
    exit_reason: tuple[PerformanceBreakdownRow, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "weekday": [
                item.to_dict()
                for item in self.weekday
            ],
            "entry_hour": [
                item.to_dict()
                for item in self.entry_hour
            ],
            "symbol": [
                item.to_dict()
                for item in self.symbol
            ],
            "exit_reason": [
                item.to_dict()
                for item in self.exit_reason
            ],
        }
