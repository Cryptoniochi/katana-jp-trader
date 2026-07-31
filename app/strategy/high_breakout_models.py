"""新高値ブレイク候補抽出の共通データモデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class HighBreakoutType(StrEnum):
    """新高値ブレイクの種別。"""

    DAY_20 = "20-day"
    DAY_60 = "60-day"
    YEAR_TO_DATE = "year-to-date"


@dataclass(frozen=True, slots=True)
class HighBreakoutScreenerSettings:
    """新高値ブレイク候補抽出条件。"""

    minimum_history_days: int = 20
    short_lookback_days: int = 20
    long_lookback_days: int = 60
    volume_lookback_days: int = 20
    atr_lookback_days: int = 14
    minimum_volume_ratio: float = 1.5
    minimum_turnover: float = 100_000_000.0
    minimum_price: float | None = 300.0
    maximum_price: float | None = 20_000.0
    minimum_atr_rate: float | None = 0.01
    maximum_atr_rate: float | None = 0.10

    def __post_init__(self) -> None:
        integer_fields = {
            "最低履歴日数": self.minimum_history_days,
            "短期高値期間": self.short_lookback_days,
            "長期高値期間": self.long_lookback_days,
            "出来高平均期間": self.volume_lookback_days,
            "ATR期間": self.atr_lookback_days,
        }

        for name, value in integer_fields.items():
            if value <= 0:
                raise ValueError(
                    f"{name}は0より大きい必要があります。"
                )

        if self.long_lookback_days < self.short_lookback_days:
            raise ValueError(
                "長期高値期間は短期高値期間以上にしてください。"
            )

        positive_optional = {
            "最低出来高倍率": self.minimum_volume_ratio,
            "最低株価": self.minimum_price,
            "最高株価": self.maximum_price,
            "最低ATR率": self.minimum_atr_rate,
            "最高ATR率": self.maximum_atr_rate,
        }

        for name, value in positive_optional.items():
            if value is not None and value <= 0:
                raise ValueError(
                    f"{name}は0より大きい必要があります。"
                )

        if self.minimum_turnover < 0:
            raise ValueError(
                "最低売買代金は0以上である必要があります。"
            )

        if (
            self.minimum_price is not None
            and self.maximum_price is not None
            and self.minimum_price > self.maximum_price
        ):
            raise ValueError(
                "最低株価は最高株価以下にしてください。"
            )

        if (
            self.minimum_atr_rate is not None
            and self.maximum_atr_rate is not None
            and self.minimum_atr_rate > self.maximum_atr_rate
        ):
            raise ValueError(
                "最低ATR率は最高ATR率以下にしてください。"
            )


@dataclass(frozen=True, slots=True)
class HighBreakoutCandidate:
    """抽出された1銘柄の新高値候補。"""

    code: str
    trading_date: date
    breakout_types: tuple[HighBreakoutType, ...]
    close_price: float
    previous_20_day_high: float | None
    previous_60_day_high: float | None
    previous_year_high: float | None
    volume_ratio: float
    turnover: float
    atr: float
    atr_rate: float
    score: float

    def __post_init__(self) -> None:
        normalized_code = self.code.strip()

        if not normalized_code:
            raise ValueError(
                "銘柄コードを指定してください。"
            )

        if not normalized_code.isdigit():
            raise ValueError(
                "銘柄コードは数字で指定してください。"
            )

        if len(normalized_code) not in {4, 5}:
            raise ValueError(
                "銘柄コードは4桁または5桁で指定してください。"
            )

        if not self.breakout_types:
            raise ValueError(
                "ブレイク種別を1件以上指定してください。"
            )

        if self.close_price <= 0:
            raise ValueError(
                "終値は0より大きい必要があります。"
            )

        if self.volume_ratio < 0:
            raise ValueError(
                "出来高倍率は0以上である必要があります。"
            )

        if self.turnover < 0:
            raise ValueError(
                "売買代金は0以上である必要があります。"
            )

        if self.atr < 0 or self.atr_rate < 0:
            raise ValueError(
                "ATRは0以上である必要があります。"
            )

        if not 0.0 <= self.score <= 100.0:
            raise ValueError(
                "スコアは0以上100以下である必要があります。"
            )

        object.__setattr__(
            self,
            "code",
            normalized_code,
        )
