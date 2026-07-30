"""前営業日のJ-Quants分足を当日の時計で再生するProvider。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol

from app.market.models import StockPrice


class MinuteBarDownloader(Protocol):
    """指定銘柄・日付の1分足を取得するDownloader。"""

    def download(
        self,
        code: str,
        date: str,
    ) -> list[StockPrice]:
        """1分足一覧を返す。"""


class FiveMinuteBarAggregator(Protocol):
    """1分足を5分足へ集約するAggregator。"""

    def aggregate_to_five_minutes(
        self,
        prices: list[StockPrice],
    ) -> list[StockPrice]:
        """5分足一覧を返す。"""


TradingDayPredicate = Callable[[date], bool]


@dataclass(frozen=True, slots=True)
class PreviousTradingDayReplayDiagnosticSnapshot:
    """前営業日リプレイProviderの利用状況。"""

    request_count: int
    download_count: int
    cache_hit_count: int
    downloaded_minute_bar_count: int
    generated_five_minute_bar_count: int
    source_dates: tuple[date, ...]
    target_dates: tuple[date, ...]
    symbol_count: int

    @property
    def cache_hit_rate(self) -> float:
        """全要求に占めるキャッシュヒット率を返す。"""

        if self.request_count == 0:
            return 0.0

        return self.cache_hit_count / self.request_count


class PreviousTradingDayReplayProvider:
    """前営業日の5分足を対象日の同時刻へ移して返す。"""

    def __init__(
        self,
        *,
        downloader: MinuteBarDownloader,
        aggregator: FiveMinuteBarAggregator,
        trading_day_predicate: TradingDayPredicate,
        maximum_lookback_days: int = 14,
    ) -> None:
        """取得・集約処理と取引日判定を設定する。"""

        if maximum_lookback_days <= 0:
            raise ValueError(
                "最大遡及日数は0より大きい必要があります。"
            )

        self.downloader = downloader
        self.aggregator = aggregator
        self.trading_day_predicate = trading_day_predicate
        self.maximum_lookback_days = maximum_lookback_days
        self._cache: dict[
            tuple[str, date],
            tuple[StockPrice, ...],
        ] = {}
        self._source_dates: dict[
            tuple[str, date],
            date,
        ] = {}
        self._request_count = 0
        self._download_count = 0
        self._cache_hit_count = 0
        self._downloaded_minute_bar_count = 0
        self._generated_five_minute_bar_count = 0

    def __call__(
        self,
        code: str,
        target_date: date,
    ) -> list[StockPrice]:
        """前営業日の足をtarget_dateへ移して返す。"""

        normalized_code = self._normalize_code(code)
        self._request_count += 1
        cache_key = (
            normalized_code,
            target_date,
        )
        cached = self._cache.get(cache_key)

        if cached is not None:
            self._cache_hit_count += 1
            return list(cached)

        source_date = self._previous_trading_day(
            target_date
        )
        minute_bars = self.downloader.download(
            normalized_code,
            source_date.isoformat(),
        )
        self._download_count += 1
        self._downloaded_minute_bar_count += len(
            minute_bars
        )
        five_minute_bars = (
            self.aggregator.aggregate_to_five_minutes(
                minute_bars
            )
        )
        self._generated_five_minute_bar_count += len(
            five_minute_bars
        )
        shifted = tuple(
            sorted(
                (
                    self._shift_to_target_date(
                        price,
                        target_date=target_date,
                    )
                    for price in five_minute_bars
                ),
                key=lambda item: (
                    item.datetime,
                    item.code,
                ),
            )
        )

        self._cache[cache_key] = shifted
        self._source_dates[cache_key] = source_date

        return list(shifted)

    def diagnostic_snapshot(
        self,
    ) -> PreviousTradingDayReplayDiagnosticSnapshot:
        """現在までのリプレイ利用状況を返す。"""

        source_dates = tuple(
            sorted(set(self._source_dates.values()))
        )
        target_dates = tuple(
            sorted(
                {
                    target_date
                    for _code, target_date
                    in self._source_dates
                }
            )
        )
        symbol_count = len(
            {
                code
                for code, _target_date
                in self._source_dates
            }
        )

        return PreviousTradingDayReplayDiagnosticSnapshot(
            request_count=self._request_count,
            download_count=self._download_count,
            cache_hit_count=self._cache_hit_count,
            downloaded_minute_bar_count=(
                self._downloaded_minute_bar_count
            ),
            generated_five_minute_bar_count=(
                self._generated_five_minute_bar_count
            ),
            source_dates=source_dates,
            target_dates=target_dates,
            symbol_count=symbol_count,
        )

    def source_date(
        self,
        code: str,
        target_date: date,
    ) -> date | None:
        """キャッシュ済み再生データの元営業日を返す。"""

        return self._source_dates.get(
            (
                self._normalize_code(code),
                target_date,
            )
        )

    def clear_cache(self) -> None:
        """取得済み再生データを破棄する。"""

        self._cache.clear()
        self._source_dates.clear()
        self._request_count = 0
        self._download_count = 0
        self._cache_hit_count = 0
        self._downloaded_minute_bar_count = 0
        self._generated_five_minute_bar_count = 0

    def _previous_trading_day(
        self,
        target_date: date,
    ) -> date:
        """対象日より前の直近取引日を返す。"""

        candidate = target_date - timedelta(days=1)

        for _ in range(self.maximum_lookback_days):
            if self.trading_day_predicate(candidate):
                return candidate

            candidate -= timedelta(days=1)

        raise RuntimeError(
            "前営業日を解決できませんでした。 "
            f"target_date={target_date.isoformat()} "
            f"maximum_lookback_days={self.maximum_lookback_days}"
        )

    @staticmethod
    def _shift_to_target_date(
        price: StockPrice,
        *,
        target_date: date,
    ) -> StockPrice:
        """価格足の日付だけを対象日へ置き換える。"""

        source_datetime = price.datetime
        shifted_datetime = datetime.combine(
            target_date,
            source_datetime.timetz(),
        )

        return StockPrice(
            code=price.code,
            datetime=shifted_datetime,
            open=price.open,
            high=price.high,
            low=price.low,
            close=price.close,
            volume=price.volume,
        )

    @staticmethod
    def _normalize_code(
        code: str,
    ) -> str:
        """銘柄コードを検証する。"""

        normalized = code.strip()

        if not normalized.isdigit():
            raise ValueError(
                "銘柄コードは数字で指定してください。"
            )

        if len(normalized) not in {4, 5}:
            raise ValueError(
                "銘柄コードは4桁または5桁で指定してください。"
            )

        return normalized
