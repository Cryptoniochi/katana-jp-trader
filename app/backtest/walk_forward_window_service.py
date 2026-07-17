"""Walk-Forward Optimizationの期間を生成する。"""

from __future__ import annotations

from datetime import date

from app.backtest.historical_models import (
    HistoricalBarSeries,
)
from app.backtest.walk_forward_models import (
    WalkForwardWindow,
    WalkForwardWindowPlan,
)


class WalkForwardWindowService:
    """取引日単位で学習期間と検証期間を分割する。"""

    def create_plan(
        self,
        series: HistoricalBarSeries,
        *,
        training_days: int,
        validation_days: int,
        step_days: int | None = None,
    ) -> WalkForwardWindowPlan:
        """固定長ローリングウィンドウを生成する。"""

        for name, value in {
            "学習日数": training_days,
            "検証日数": validation_days,
        }.items():
            if value <= 0:
                raise ValueError(
                    f"{name}は0より大きい必要があります。"
                )

        resolved_step_days = (
            validation_days
            if step_days is None
            else step_days
        )

        if resolved_step_days <= 0:
            raise ValueError(
                "前進日数は0より大きい必要があります。"
            )

        trading_dates = self._trading_dates(series)
        required_days = training_days + validation_days

        windows: list[WalkForwardWindow] = []
        start_index = 0

        while (
            start_index + required_days
            <= len(trading_dates)
        ):
            training_dates = trading_dates[
                start_index:
                start_index + training_days
            ]
            validation_dates = trading_dates[
                start_index + training_days:
                start_index + required_days
            ]

            training_series = self._slice_series(
                series,
                included_dates=set(training_dates),
            )
            validation_series = self._slice_series(
                series,
                included_dates=set(validation_dates),
            )

            windows.append(
                WalkForwardWindow(
                    window_number=len(windows) + 1,
                    training_start_date=training_dates[0],
                    training_end_date=training_dates[-1],
                    validation_start_date=validation_dates[0],
                    validation_end_date=validation_dates[-1],
                    training_series=training_series,
                    validation_series=validation_series,
                )
            )

            start_index += resolved_step_days

        return WalkForwardWindowPlan(
            windows=tuple(windows),
            training_days=training_days,
            validation_days=validation_days,
            step_days=resolved_step_days,
        )

    @staticmethod
    def _trading_dates(
        series: HistoricalBarSeries,
    ) -> tuple[date, ...]:
        """系列に含まれる取引日を昇順で返す。"""

        return tuple(
            sorted(
                {
                    bar.opened_at.date()
                    for bar in series.bars
                }
            )
        )

    @staticmethod
    def _slice_series(
        series: HistoricalBarSeries,
        *,
        included_dates: set[date],
    ) -> HistoricalBarSeries:
        """指定取引日のローソク足だけを抽出する。"""

        bars = tuple(
            bar
            for bar in series.bars
            if bar.opened_at.date() in included_dates
        )

        return HistoricalBarSeries(
            code=series.code,
            timeframe=series.timeframe,
            bars=bars,
        )
