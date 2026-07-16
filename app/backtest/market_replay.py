"""OHLCV履歴を時系列順に安全に再生する。"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator

from app.backtest.historical_models import (
    HistoricalBar,
    HistoricalBarSeries,
    MarketTimeframe,
)


@dataclass(frozen=True, slots=True)
class MarketReplayFrame:
    """ある時点で戦略へ公開できる市場履歴。"""

    current_bar: HistoricalBar
    visible_bars: tuple[
        HistoricalBar,
        ...
    ]
    index: int
    total_count: int

    def __post_init__(self) -> None:
        """リプレイFrameの整合性を検証する。"""

        if self.index < 0:
            raise ValueError(
                "リプレイ位置は0以上である必要があります。"
            )

        if self.total_count <= 0:
            raise ValueError(
                "総件数は0より大きい必要があります。"
            )

        if self.index >= self.total_count:
            raise ValueError(
                "リプレイ位置は総件数未満である必要があります。"
            )

        if not self.visible_bars:
            raise ValueError(
                "公開履歴には現在足が必要です。"
            )

        if self.visible_bars[-1] != self.current_bar:
            raise ValueError(
                "公開履歴の末尾は現在足である必要があります。"
            )

        if any(
            bar.opened_at > self.current_bar.opened_at
            for bar in self.visible_bars
        ):
            raise ValueError(
                "公開履歴に未来のローソク足を含められません。"
            )

    @property
    def replayed_at(self) -> datetime:
        """現在足の終了日時をUTCで返す。"""

        return self.current_bar.closed_at.astimezone(
            timezone.utc
        )

    @property
    def code(self) -> str:
        """銘柄コードを返す。"""

        return self.current_bar.code

    @property
    def timeframe(self) -> MarketTimeframe:
        """時間軸を返す。"""

        return self.current_bar.timeframe

    @property
    def is_first(self) -> bool:
        """最初のFrameか返す。"""

        return self.index == 0

    @property
    def is_last(self) -> bool:
        """最後のFrameか返す。"""

        return self.index == self.total_count - 1


@dataclass(frozen=True, slots=True)
class MarketReplaySettings:
    """時系列リプレイの抽出条件。"""

    start_at: datetime | None = None
    end_at: datetime | None = None
    warmup_bars: int = 0

    def __post_init__(self) -> None:
        """抽出期間とウォームアップ件数を検証する。"""

        if (
            self.start_at is not None
            and self.start_at.tzinfo is None
        ):
            raise ValueError(
                "開始日時にはタイムゾーンが必要です。"
            )

        if (
            self.end_at is not None
            and self.end_at.tzinfo is None
        ):
            raise ValueError(
                "終了日時にはタイムゾーンが必要です。"
            )

        if (
            self.start_at is not None
            and self.end_at is not None
            and self.end_at < self.start_at
        ):
            raise ValueError(
                "終了日時は開始日時以後である必要があります。"
            )

        if self.warmup_bars < 0:
            raise ValueError(
                "ウォームアップ件数は0以上である必要があります。"
            )


class MarketReplayEngine:
    """履歴データを未来参照なしで1本ずつ再生する。"""

    def __init__(
        self,
        series: HistoricalBarSeries,
        *,
        settings: MarketReplaySettings | None = None,
    ) -> None:
        """履歴系列と再生条件を設定する。"""

        self.series = series
        self.settings = (
            settings
            if settings is not None
            else MarketReplaySettings()
        )

    def frames(self) -> Iterator[MarketReplayFrame]:
        """条件に一致するFrameを時系列順に返す。"""

        selected_indexes = self._selected_indexes()
        total_count = len(selected_indexes)

        for replay_index, source_index in enumerate(
            selected_indexes
        ):
            current_bar = self.series.bars[source_index]

            yield MarketReplayFrame(
                current_bar=current_bar,
                visible_bars=self.series.bars[
                    : source_index + 1
                ],
                index=replay_index,
                total_count=total_count,
            )

    def replay(self) -> tuple[MarketReplayFrame, ...]:
        """すべてのFrameをタプルで返す。"""

        return tuple(self.frames())

    def _selected_indexes(self) -> list[int]:
        """再生対象となる元系列上の位置を返す。"""

        indexes: list[int] = []

        for index, bar in enumerate(self.series.bars):
            if index < self.settings.warmup_bars:
                continue

            if (
                self.settings.start_at is not None
                and bar.opened_at < self.settings.start_at
            ):
                continue

            if (
                self.settings.end_at is not None
                and bar.opened_at > self.settings.end_at
            ):
                continue

            indexes.append(index)

        return indexes
