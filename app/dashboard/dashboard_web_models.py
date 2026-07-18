"""Read-only Web Dashboardの表示モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class DashboardDailyPoint:
    """日次損益・純資産・Drawdown推移の1点。"""

    trading_date: date
    net_profit_loss: float | None
    final_equity: float | None
    return_rate: float | None
    cumulative_profit_loss: float = 0.0
    cumulative_return: float | None = None
    drawdown: float | None = None

    def __post_init__(self) -> None:
        """日次指標を検証する。"""

        if (
            self.drawdown is not None
            and self.drawdown < 0
        ):
            raise ValueError(
                "Drawdownは0以上である必要があります。"
            )

    def to_dict(self) -> dict[str, Any]:
        """JSON互換辞書へ変換する。"""

        return {
            "trading_date": self.trading_date.isoformat(),
            "net_profit_loss": self.net_profit_loss,
            "final_equity": self.final_equity,
            "return_rate": self.return_rate,
            "cumulative_profit_loss": (
                self.cumulative_profit_loss
            ),
            "cumulative_return": self.cumulative_return,
            "drawdown": self.drawdown,
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

    @property
    def latest_daily_point(
        self,
    ) -> DashboardDailyPoint | None:
        """最新営業日の指標を返す。"""

        if not self.daily_history:
            return None

        return self.daily_history[-1]

    @property
    def maximum_drawdown(self) -> float | None:
        """日次純資産系列の最大Drawdownを返す。"""

        values = [
            point.drawdown
            for point in self.daily_history
            if point.drawdown is not None
        ]

        if not values:
            return None

        return max(values)

    @property
    def winning_day_count(self) -> int:
        """日次損益がプラスの営業日数を返す。"""

        return sum(
            point.net_profit_loss is not None
            and point.net_profit_loss > 0
            for point in self.daily_history
        )

    @property
    def losing_day_count(self) -> int:
        """日次損益がマイナスの営業日数を返す。"""

        return sum(
            point.net_profit_loss is not None
            and point.net_profit_loss < 0
            for point in self.daily_history
        )

    @property
    def daily_win_rate(self) -> float | None:
        """損益が確定した営業日ベースの勝率を返す。"""

        denominator = (
            self.winning_day_count
            + self.losing_day_count
        )

        if denominator == 0:
            return None

        return self.winning_day_count / denominator

    def to_dict(self) -> dict[str, Any]:
        """JSON互換辞書へ変換する。"""

        latest = self.latest_daily_point

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
            "analytics": {
                "trading_day_count": len(
                    self.daily_history
                ),
                "winning_day_count": (
                    self.winning_day_count
                ),
                "losing_day_count": (
                    self.losing_day_count
                ),
                "daily_win_rate": self.daily_win_rate,
                "maximum_drawdown": (
                    self.maximum_drawdown
                ),
                "latest_cumulative_return": (
                    latest.cumulative_return
                    if latest is not None
                    else None
                ),
            },
        }
