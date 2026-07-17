"""Walk-Forward Optimizationの期間モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.backtest.historical_models import (
    HistoricalBarSeries,
)


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    """1回分の学習期間と検証期間。"""

    window_number: int
    training_start_date: date
    training_end_date: date
    validation_start_date: date
    validation_end_date: date
    training_series: HistoricalBarSeries
    validation_series: HistoricalBarSeries

    def __post_init__(self) -> None:
        """期間・系列の整合性を検証する。"""

        if self.window_number <= 0:
            raise ValueError(
                "ウィンドウ番号は0より大きい必要があります。"
            )

        if self.training_end_date < self.training_start_date:
            raise ValueError(
                "学習期間終了日は開始日以後である必要があります。"
            )

        if self.validation_end_date < self.validation_start_date:
            raise ValueError(
                "検証期間終了日は開始日以後である必要があります。"
            )

        if self.validation_start_date <= self.training_end_date:
            raise ValueError(
                "検証期間は学習期間終了後に開始する必要があります。"
            )

        if self.training_series.code != self.validation_series.code:
            raise ValueError(
                "学習系列と検証系列の銘柄コードが一致しません。"
            )

        if (
            self.training_series.timeframe
            is not self.validation_series.timeframe
        ):
            raise ValueError(
                "学習系列と検証系列の時間軸が一致しません。"
            )

        if not self.training_series.bars:
            raise ValueError(
                "学習系列は1件以上のローソク足が必要です。"
            )

        if not self.validation_series.bars:
            raise ValueError(
                "検証系列は1件以上のローソク足が必要です。"
            )

        training_dates = {
            bar.opened_at.date()
            for bar in self.training_series.bars
        }
        validation_dates = {
            bar.opened_at.date()
            for bar in self.validation_series.bars
        }

        if min(training_dates) != self.training_start_date:
            raise ValueError(
                "学習系列の開始日が学習期間と一致しません。"
            )

        if max(training_dates) != self.training_end_date:
            raise ValueError(
                "学習系列の終了日が学習期間と一致しません。"
            )

        if min(validation_dates) != self.validation_start_date:
            raise ValueError(
                "検証系列の開始日が検証期間と一致しません。"
            )

        if max(validation_dates) != self.validation_end_date:
            raise ValueError(
                "検証系列の終了日が検証期間と一致しません。"
            )

    @property
    def window_id(self) -> str:
        """再現可能なウィンドウIDを返す。"""

        return (
            f"wf-{self.window_number:03d}_"
            f"train-{self.training_start_date.isoformat()}-"
            f"{self.training_end_date.isoformat()}_"
            f"validate-{self.validation_start_date.isoformat()}-"
            f"{self.validation_end_date.isoformat()}"
        )

    @property
    def code(self) -> str:
        """対象銘柄コードを返す。"""

        return self.training_series.code

    @property
    def training_trading_day_count(self) -> int:
        """学習期間の取引日数を返す。"""

        return len(
            {
                bar.opened_at.date()
                for bar in self.training_series.bars
            }
        )

    @property
    def validation_trading_day_count(self) -> int:
        """検証期間の取引日数を返す。"""

        return len(
            {
                bar.opened_at.date()
                for bar in self.validation_series.bars
            }
        )


@dataclass(frozen=True, slots=True)
class WalkForwardWindowPlan:
    """Walk-Forwardで使用する全ウィンドウ。"""

    windows: tuple[WalkForwardWindow, ...]
    training_days: int
    validation_days: int
    step_days: int

    def __post_init__(self) -> None:
        """設定値とウィンドウ順序を検証する。"""

        for name, value in {
            "学習日数": self.training_days,
            "検証日数": self.validation_days,
            "前進日数": self.step_days,
        }.items():
            if value <= 0:
                raise ValueError(
                    f"{name}は0より大きい必要があります。"
                )

        expected_numbers = list(
            range(1, len(self.windows) + 1)
        )
        actual_numbers = [
            window.window_number
            for window in self.windows
        ]

        if actual_numbers != expected_numbers:
            raise ValueError(
                "ウィンドウ番号は1からの連番で指定してください。"
            )

        window_ids = [
            window.window_id
            for window in self.windows
        ]

        if len(window_ids) != len(set(window_ids)):
            raise ValueError(
                "Walk-ForwardウィンドウIDが重複しています。"
            )

    @property
    def window_count(self) -> int:
        """ウィンドウ件数を返す。"""

        return len(self.windows)

    def get(
        self,
        window_id: str,
    ) -> WalkForwardWindow:
        """ウィンドウIDに一致する結果を返す。"""

        normalized = window_id.strip()

        if not normalized:
            raise ValueError(
                "ウィンドウIDを指定してください。"
            )

        for window in self.windows:
            if window.window_id == normalized:
                return window

        raise KeyError(
            "指定されたWalk-Forwardウィンドウが存在しません。 "
            f"window_id={normalized}"
        )
