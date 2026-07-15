"""ORB戦略で共通利用する条件プロファイル。"""

from dataclasses import dataclass
from datetime import time

from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


@dataclass(frozen=True, slots=True)
class OrbStrategyProfile:
    """ORB戦略の共通条件を保持する。"""

    quantity: int = 100
    opening_range_end: time = time(9, 15)
    stop_loss_rate: float = 0.01
    take_profit_rate: float = 0.02
    force_exit_time: time = time(14, 50)

    commission: float = 0.0
    slippage_rate: float = 0.0005

    min_opening_range_volume: int | None = 200_000
    min_breakout_volume: int | None = 50_000
    breakout_volume_ratio: float | None = 0.8

    min_price: float | None = 500.0
    max_price: float | None = 20_000.0

    min_opening_range_turnover: float | None = 200_000_000.0
    min_breakout_turnover: float | None = 50_000_000.0

    def create_strategy(
        self,
        *,
        opening_range_end: time | None = None,
        stop_loss_rate: float | None = None,
        take_profit_rate: float | None = None,
    ) -> OpeningRangeBreakoutStrategy:
        """プロファイルからORB戦略を作成する。"""

        return OpeningRangeBreakoutStrategy(
            quantity=self.quantity,
            opening_range_end=(
                opening_range_end
                if opening_range_end is not None
                else self.opening_range_end
            ),
            stop_loss_rate=(
                stop_loss_rate if stop_loss_rate is not None else self.stop_loss_rate
            ),
            take_profit_rate=(
                take_profit_rate
                if take_profit_rate is not None
                else self.take_profit_rate
            ),
            force_exit_time=self.force_exit_time,
            commission=self.commission,
            slippage_rate=self.slippage_rate,
            min_opening_range_volume=(self.min_opening_range_volume),
            min_breakout_volume=self.min_breakout_volume,
            breakout_volume_ratio=self.breakout_volume_ratio,
            min_price=self.min_price,
            max_price=self.max_price,
            min_opening_range_turnover=(self.min_opening_range_turnover),
            min_breakout_turnover=(self.min_breakout_turnover),
        )


DEFAULT_ORB_PROFILE = OrbStrategyProfile()
