"""ORB最適化パラメータの組み合わせを生成する。"""

from collections.abc import Iterable
from datetime import time
from itertools import product

from app.backtest.optimization_models import (
    OrbOptimizationGrid,
    OrbOptimizationParameters,
)


class OrbOptimizationGridService:
    """ORBパラメータ候補から直積グリッドを作成する。"""

    def create_grid(
        self,
        *,
        stop_loss_rates: Iterable[float | None],
        take_profit_rates: Iterable[float | None],
        opening_range_ends: Iterable[time],
        maximum_combinations: int = 10_000,
    ) -> OrbOptimizationGrid:
        """候補値を正規化して全組み合わせを返す。"""

        if maximum_combinations <= 0:
            raise ValueError(
                "最大組み合わせ件数は0より大きい必要があります。"
            )

        normalized_stop_losses = self._normalize_rates(
            stop_loss_rates,
            name="損切り率",
        )
        normalized_take_profits = self._normalize_rates(
            take_profit_rates,
            name="利確率",
        )
        normalized_opening_ranges = (
            self._normalize_times(
                opening_range_ends
            )
        )

        combination_count = (
            len(normalized_stop_losses)
            * len(normalized_take_profits)
            * len(normalized_opening_ranges)
        )

        if combination_count > maximum_combinations:
            raise ValueError(
                "最適化パラメータの組み合わせ件数が"
                "上限を超えています。 "
                f"count={combination_count} "
                f"maximum={maximum_combinations}"
            )

        parameters = tuple(
            OrbOptimizationParameters(
                stop_loss_rate=stop_loss_rate,
                take_profit_rate=take_profit_rate,
                opening_range_end=opening_range_end,
            )
            for (
                stop_loss_rate,
                take_profit_rate,
                opening_range_end,
            ) in product(
                normalized_stop_losses,
                normalized_take_profits,
                normalized_opening_ranges,
            )
        )

        return OrbOptimizationGrid(
            parameters=parameters
        )

    @staticmethod
    def _normalize_rates(
        values: Iterable[float | None],
        *,
        name: str,
    ) -> tuple[float | None, ...]:
        """率候補を重複なし・安定順序へ正規化する。"""

        materialized = tuple(values)

        if not materialized:
            raise ValueError(
                f"{name}候補を1件以上指定してください。"
            )

        normalized: list[float | None] = []

        for value in materialized:
            if value is not None and value <= 0:
                raise ValueError(
                    f"{name}は0より大きい必要があります。"
                )

            if value not in normalized:
                normalized.append(value)

        return tuple(normalized)

    @staticmethod
    def _normalize_times(
        values: Iterable[time],
    ) -> tuple[time, ...]:
        """時刻候補を重複なし・安定順序へ正規化する。"""

        materialized = tuple(values)

        if not materialized:
            raise ValueError(
                "オープニングレンジ終了時刻候補を"
                "1件以上指定してください。"
            )

        normalized: list[time] = []

        for value in materialized:
            if value not in normalized:
                normalized.append(value)

        return tuple(normalized)
