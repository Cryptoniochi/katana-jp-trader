"""日足から新高値ブレイク候補を抽出する。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from app.backtest.historical_models import (
    HistoricalBar,
    HistoricalBarSeries,
    MarketTimeframe,
)
from app.strategy.high_breakout_models import (
    HighBreakoutCandidate,
    HighBreakoutScreenerSettings,
    HighBreakoutType,
)


class HighBreakoutScreener:
    """1銘柄の日足系列から候補を判定する。"""

    def __init__(
        self,
        *,
        settings: HighBreakoutScreenerSettings | None = None,
    ) -> None:
        self.settings = (
            settings
            if settings is not None
            else HighBreakoutScreenerSettings()
        )

    def screen(
        self,
        series: HistoricalBarSeries,
    ) -> HighBreakoutCandidate | None:
        """最新日足を評価して候補を返す。"""

        if series.timeframe is not MarketTimeframe.DAY_1:
            raise ValueError(
                "新高値ブレイク抽出は日足のみ対応しています。"
            )

        bars = series.bars
        required = max(
            self.settings.minimum_history_days,
            self.settings.short_lookback_days + 1,
            self.settings.volume_lookback_days + 1,
            self.settings.atr_lookback_days + 1,
        )

        if len(bars) < required:
            return None

        current = bars[-1]
        history = bars[:-1]

        if not self._passes_price_filter(
            current.close_price
        ):
            return None

        previous_20 = self._previous_high(
            history,
            self.settings.short_lookback_days,
        )
        previous_60 = (
            self._previous_high(
                history,
                self.settings.long_lookback_days,
            )
            if len(history)
            >= self.settings.long_lookback_days
            else None
        )
        previous_year = self._previous_year_high(
            history,
            current.opened_at.date(),
        )

        breakout_types: list[HighBreakoutType] = []

        if (
            previous_20 is not None
            and current.close_price > previous_20
        ):
            breakout_types.append(
                HighBreakoutType.DAY_20
            )

        if (
            previous_60 is not None
            and current.close_price > previous_60
        ):
            breakout_types.append(
                HighBreakoutType.DAY_60
            )

        if (
            previous_year is not None
            and current.close_price > previous_year
        ):
            breakout_types.append(
                HighBreakoutType.YEAR_TO_DATE
            )

        if not breakout_types:
            return None

        average_volume = self._average_volume(
            history,
            self.settings.volume_lookback_days,
        )
        volume_ratio = (
            current.volume / average_volume
            if average_volume > 0
            else 0.0
        )

        if (
            volume_ratio
            < self.settings.minimum_volume_ratio
        ):
            return None

        turnover = (
            current.close_price
            * current.volume
        )

        if turnover < self.settings.minimum_turnover:
            return None

        atr = self._average_true_range(
            bars,
            self.settings.atr_lookback_days,
        )
        atr_rate = (
            atr / current.close_price
            if current.close_price > 0
            else 0.0
        )

        if (
            self.settings.minimum_atr_rate is not None
            and atr_rate < self.settings.minimum_atr_rate
        ):
            return None

        if (
            self.settings.maximum_atr_rate is not None
            and atr_rate > self.settings.maximum_atr_rate
        ):
            return None

        score = self._score(
            breakout_types=tuple(breakout_types),
            volume_ratio=volume_ratio,
            atr_rate=atr_rate,
            turnover=turnover,
        )

        return HighBreakoutCandidate(
            code=series.code,
            trading_date=current.opened_at.date(),
            breakout_types=tuple(breakout_types),
            close_price=current.close_price,
            previous_20_day_high=previous_20,
            previous_60_day_high=previous_60,
            previous_year_high=previous_year,
            volume_ratio=volume_ratio,
            turnover=turnover,
            atr=atr,
            atr_rate=atr_rate,
            score=score,
        )

    def screen_many(
        self,
        series_collection: Iterable[
            HistoricalBarSeries
        ],
    ) -> tuple[HighBreakoutCandidate, ...]:
        """複数銘柄を評価しスコア順で返す。"""

        candidates = tuple(
            candidate
            for series in series_collection
            if (
                candidate := self.screen(series)
            ) is not None
        )

        return tuple(
            sorted(
                candidates,
                key=lambda item: (
                    -item.score,
                    -len(item.breakout_types),
                    -item.volume_ratio,
                    item.code,
                ),
            )
        )

    def _passes_price_filter(
        self,
        price: float,
    ) -> bool:
        if (
            self.settings.minimum_price is not None
            and price < self.settings.minimum_price
        ):
            return False

        if (
            self.settings.maximum_price is not None
            and price > self.settings.maximum_price
        ):
            return False

        return True

    @staticmethod
    def _previous_high(
        history: tuple[HistoricalBar, ...],
        lookback_days: int,
    ) -> float | None:
        if len(history) < lookback_days:
            return None

        return max(
            bar.high_price
            for bar in history[-lookback_days:]
        )

    @staticmethod
    def _previous_year_high(
        history: tuple[HistoricalBar, ...],
        trading_date: date,
    ) -> float | None:
        same_year = tuple(
            bar
            for bar in history
            if bar.opened_at.date().year
            == trading_date.year
        )

        if not same_year:
            return None

        return max(
            bar.high_price
            for bar in same_year
        )

    @staticmethod
    def _average_volume(
        history: tuple[HistoricalBar, ...],
        lookback_days: int,
    ) -> float:
        selected = history[-lookback_days:]

        if not selected:
            return 0.0

        return sum(
            bar.volume
            for bar in selected
        ) / len(selected)

    @staticmethod
    def _average_true_range(
        bars: tuple[HistoricalBar, ...],
        lookback_days: int,
    ) -> float:
        selected = bars[
            -(lookback_days + 1):
        ]

        if len(selected) < 2:
            return 0.0

        true_ranges: list[float] = []

        for previous, current in zip(
            selected,
            selected[1:],
        ):
            true_ranges.append(
                max(
                    current.high_price
                    - current.low_price,
                    abs(
                        current.high_price
                        - previous.close_price
                    ),
                    abs(
                        current.low_price
                        - previous.close_price
                    ),
                )
            )

        return (
            sum(true_ranges)
            / len(true_ranges)
        )

    @staticmethod
    def _score(
        *,
        breakout_types: tuple[HighBreakoutType, ...],
        volume_ratio: float,
        atr_rate: float,
        turnover: float,
    ) -> float:
        breakout_score = min(
            45.0,
            15.0 * len(breakout_types),
        )
        volume_score = min(
            25.0,
            volume_ratio * 10.0,
        )
        atr_score = min(
            15.0,
            atr_rate * 300.0,
        )
        turnover_score = min(
            15.0,
            turnover / 1_000_000_000.0 * 15.0,
        )

        return round(
            min(
                100.0,
                breakout_score
                + volume_score
                + atr_score
                + turnover_score,
            ),
            4,
        )
