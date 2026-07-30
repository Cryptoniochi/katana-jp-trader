"""リアルタイムTickから時間足を生成する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from app.market.market_data_provider import MarketDataTick


@dataclass(frozen=True, slots=True)
class RealtimeBar:
    """リアルタイム集計されたOHLCVバー。"""

    code: str
    started_at: datetime
    ended_at: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    exchange: int = 1

    def __post_init__(self) -> None:
        """バー値を検証する。"""

        if self.started_at.tzinfo is None:
            raise ValueError(
                "開始日時にはタイムゾーンが必要です。"
            )
        if self.ended_at.tzinfo is None:
            raise ValueError(
                "終了日時にはタイムゾーンが必要です。"
            )
        if self.ended_at <= self.started_at:
            raise ValueError(
                "終了日時は開始日時より後である必要があります。"
            )
        if self.volume < 0:
            raise ValueError(
                "出来高は0以上である必要があります。"
            )


@dataclass(slots=True)
class _WorkingBar:
    """集計途中のバー。"""

    code: str
    started_at: datetime
    ended_at: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    exchange: int

    def update(
        self,
        *,
        price: float,
        incremental_volume: float,
    ) -> None:
        """現在値と出来高を反映する。"""

        self.high_price = max(self.high_price, price)
        self.low_price = min(self.low_price, price)
        self.close_price = price
        self.volume += incremental_volume

    def freeze(self) -> RealtimeBar:
        """不変バーへ変換する。"""

        return RealtimeBar(
            code=self.code,
            started_at=self.started_at,
            ended_at=self.ended_at,
            open_price=self.open_price,
            high_price=self.high_price,
            low_price=self.low_price,
            close_price=self.close_price,
            volume=self.volume,
            exchange=self.exchange,
        )


class RealtimeBarAggregator:
    """銘柄別に累積出来高から時間足を生成する。"""

    def __init__(
        self,
        *,
        interval_minutes: int = 5,
        on_completed_bar: Callable[
            [RealtimeBar], None
        ] | None = None,
    ) -> None:
        """時間足間隔と完成バー通知先を保持する。"""

        if interval_minutes <= 0:
            raise ValueError(
                "足間隔は1分以上である必要があります。"
            )
        if 60 % interval_minutes != 0:
            raise ValueError(
                "足間隔は60を割り切れる値にしてください。"
            )

        self.interval_minutes = interval_minutes
        self.on_completed_bar = on_completed_bar
        self._working: dict[str, _WorkingBar] = {}
        self._last_cumulative_volume: dict[str, float] = {}
        self._last_tick_at: dict[str, datetime] = {}

    def ingest(
        self,
        tick: MarketDataTick,
    ) -> RealtimeBar | None:
        """Tickを取り込み、足確定時は完成バーを返す。"""

        last_tick_at = self._last_tick_at.get(tick.code)
        if (
            last_tick_at is not None
            and tick.observed_at <= last_tick_at
        ):
            return None

        self._last_tick_at[tick.code] = tick.observed_at

        incremental_volume = (
            self._calculate_incremental_volume(tick)
        )
        started_at = _floor_datetime(
            tick.observed_at,
            self.interval_minutes,
        )
        ended_at = started_at + timedelta(
            minutes=self.interval_minutes
        )
        current = self._working.get(tick.code)

        if current is None:
            self._working[tick.code] = _WorkingBar(
                code=tick.code,
                started_at=started_at,
                ended_at=ended_at,
                open_price=tick.price,
                high_price=tick.price,
                low_price=tick.price,
                close_price=tick.price,
                volume=incremental_volume,
                exchange=tick.exchange,
            )
            return None

        if current.started_at == started_at:
            current.update(
                price=tick.price,
                incremental_volume=incremental_volume,
            )
            return None

        completed = current.freeze()
        self._working[tick.code] = _WorkingBar(
            code=tick.code,
            started_at=started_at,
            ended_at=ended_at,
            open_price=tick.price,
            high_price=tick.price,
            low_price=tick.price,
            close_price=tick.price,
            volume=incremental_volume,
            exchange=tick.exchange,
        )
        self._notify(completed)
        return completed

    def flush_all(self) -> tuple[RealtimeBar, ...]:
        """集計途中の全バーを完成扱いで返す。"""

        bars = tuple(
            working.freeze()
            for working in self._working.values()
        )
        self._working.clear()

        for bar in bars:
            self._notify(bar)

        return bars

    def _calculate_incremental_volume(
        self,
        tick: MarketDataTick,
    ) -> float:
        """累積出来高から今回増分を計算する。"""

        cumulative = tick.cumulative_volume
        if cumulative is None:
            return 0.0

        previous = self._last_cumulative_volume.get(
            tick.code
        )
        self._last_cumulative_volume[
            tick.code
        ] = cumulative

        if previous is None:
            return 0.0

        if cumulative < previous:
            return 0.0

        return cumulative - previous

    def _notify(self, bar: RealtimeBar) -> None:
        """完成バーを通知する。"""

        if self.on_completed_bar is not None:
            self.on_completed_bar(bar)


def _floor_datetime(
    value: datetime,
    interval_minutes: int,
) -> datetime:
    """日時を指定分足の開始時刻へ切り下げる。"""

    minute = (
        value.minute // interval_minutes
    ) * interval_minutes
    return value.replace(
        minute=minute,
        second=0,
        microsecond=0,
    )
