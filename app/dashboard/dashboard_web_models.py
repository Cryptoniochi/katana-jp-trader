"""Read-only Web Dashboardの表示モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class DashboardDailyPoint:
    """日次損益・純資産推移の1点。"""

    trading_date: date
    net_profit_loss: float | None
    final_equity: float | None
    return_rate: float | None

    def to_dict(self) -> dict[str, Any]:
        """JSON互換辞書へ変換する。"""

        return {
            "trading_date": self.trading_date.isoformat(),
            "net_profit_loss": self.net_profit_loss,
            "final_equity": self.final_equity,
            "return_rate": self.return_rate,
        }


@dataclass(frozen=True, slots=True)
class DashboardWebPayload:
    """Web Dashboard v1のRead-only Payload。"""

    generated_at: datetime
    snapshot: dict[str, Any]
    daily_history: tuple[DashboardDailyPoint, ...]
    cumulative_profit_loss: float

    def __post_init__(self) -> None:
        """生成日時を検証する。"""

        if self.generated_at.tzinfo is None:
            raise ValueError(
                "Dashboard生成日時にはタイムゾーンが必要です。"
            )

    def to_dict(self) -> dict[str, Any]:
        """JSON互換辞書へ変換する。"""

        return {
            "generated_at": self.generated_at.isoformat(),
            "snapshot": self.snapshot,
            "daily_history": [
                point.to_dict()
                for point in self.daily_history
            ],
            "cumulative_profit_loss": (
                self.cumulative_profit_loss
            ),
        }
