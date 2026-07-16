"""バックテスト用OHLCV履歴の共通データモデル。"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class MarketTimeframe(StrEnum):
    """対応するローソク足の時間軸。"""

    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    DAY_1 = "1d"

    @property
    def duration(self) -> timedelta:
        """時間軸に対応する期間を返す。"""

        durations = {
            MarketTimeframe.MINUTE_1: timedelta(minutes=1),
            MarketTimeframe.MINUTE_5: timedelta(minutes=5),
            MarketTimeframe.MINUTE_15: timedelta(minutes=15),
            MarketTimeframe.MINUTE_30: timedelta(minutes=30),
            MarketTimeframe.HOUR_1: timedelta(hours=1),
            MarketTimeframe.DAY_1: timedelta(days=1),
        }

        return durations[self]


@dataclass(frozen=True, slots=True)
class HistoricalBar:
    """1銘柄・1期間のOHLCV履歴。"""

    code: str
    timeframe: MarketTimeframe
    opened_at: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float

    def __post_init__(self) -> None:
        """OHLCV内容を検証して文字列を正規化する。"""

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

        if self.opened_at.tzinfo is None:
            raise ValueError(
                "開始日時にはタイムゾーンが必要です。"
            )

        prices = {
            "始値": self.open_price,
            "高値": self.high_price,
            "安値": self.low_price,
            "終値": self.close_price,
        }

        for name, value in prices.items():
            if value <= 0:
                raise ValueError(
                    f"{name}は0より大きい必要があります。"
                )

        if self.volume < 0:
            raise ValueError(
                "出来高は0以上である必要があります。"
            )

        if self.high_price < self.low_price:
            raise ValueError(
                "高値は安値以上である必要があります。"
            )

        if not (
            self.low_price
            <= self.open_price
            <= self.high_price
        ):
            raise ValueError(
                "始値は安値以上かつ高値以下である必要があります。"
            )

        if not (
            self.low_price
            <= self.close_price
            <= self.high_price
        ):
            raise ValueError(
                "終値は安値以上かつ高値以下である必要があります。"
            )

        object.__setattr__(
            self,
            "code",
            normalized_code,
        )

    @property
    def closed_at(self) -> datetime:
        """ローソク足の終了日時を返す。"""

        return self.opened_at + self.timeframe.duration

    @property
    def typical_price(self) -> float:
        """高値・安値・終値の平均価格を返す。"""

        return (
            self.high_price
            + self.low_price
            + self.close_price
        ) / 3.0

    @property
    def price_range(self) -> float:
        """高値と安値の値幅を返す。"""

        return self.high_price - self.low_price


@dataclass(frozen=True, slots=True)
class HistoricalBarSeries:
    """同一銘柄・同一時間軸の時系列OHLCV。"""

    code: str
    timeframe: MarketTimeframe
    bars: tuple[
        HistoricalBar,
        ...
    ]

    def __post_init__(self) -> None:
        """系列の銘柄・時間軸・順序・重複を検証する。"""

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

        previous_opened_at: datetime | None = None

        for bar in self.bars:
            if bar.code != normalized_code:
                raise ValueError(
                    "系列とローソク足の銘柄コードが"
                    "一致しません。"
                )

            if bar.timeframe is not self.timeframe:
                raise ValueError(
                    "系列とローソク足の時間軸が"
                    "一致しません。"
                )

            if (
                previous_opened_at is not None
                and bar.opened_at <= previous_opened_at
            ):
                raise ValueError(
                    "ローソク足は開始日時の昇順かつ"
                    "重複なしで指定してください。"
                )

            previous_opened_at = bar.opened_at

        object.__setattr__(
            self,
            "code",
            normalized_code,
        )

    @property
    def bar_count(self) -> int:
        """ローソク足件数を返す。"""

        return len(self.bars)

    @property
    def started_at(self) -> datetime | None:
        """最初のローソク足の開始日時を返す。"""

        if not self.bars:
            return None

        return self.bars[0].opened_at

    @property
    def ended_at(self) -> datetime | None:
        """最後のローソク足の終了日時を返す。"""

        if not self.bars:
            return None

        return self.bars[-1].closed_at
