"""株価の短時間足を長時間足へ集約する処理。"""

from collections import defaultdict
from datetime import datetime, timedelta

from app.market.models import StockPrice


class BarAggregationError(ValueError):
    """ローソク足の集約に失敗したことを表す。"""


class StockPriceAggregator:
    """StockPriceの一覧を指定分数のローソク足へ集約する。"""

    def aggregate(
        self,
        prices: list[StockPrice],
        interval_minutes: int,
    ) -> list[StockPrice]:
        """株価を指定した分数の時間足へ集約する。"""

        if interval_minutes <= 0:
            raise ValueError("集約間隔は0より大きい必要があります。")

        if interval_minutes > 60:
            raise ValueError("集約間隔は60分以下で指定してください。")

        if not prices:
            return []

        grouped_prices: dict[
            tuple[str, datetime],
            list[StockPrice],
        ] = defaultdict(list)

        for price in prices:
            bucket_start = self._calculate_bucket_start(
                traded_at=price.datetime,
                interval_minutes=interval_minutes,
            )

            key = (
                price.code,
                bucket_start,
            )
            grouped_prices[key].append(price)

        aggregated_prices: list[StockPrice] = []

        for (
            code,
            bucket_start,
        ), group in grouped_prices.items():
            sorted_group = sorted(
                group,
                key=lambda price: price.datetime,
            )

            first_price = sorted_group[0]
            last_price = sorted_group[-1]

            aggregated_prices.append(
                StockPrice(
                    code=code,
                    datetime=bucket_start,
                    open=first_price.open,
                    high=max(price.high for price in sorted_group),
                    low=min(price.low for price in sorted_group),
                    close=last_price.close,
                    volume=sum(price.volume for price in sorted_group),
                )
            )

        return sorted(
            aggregated_prices,
            key=lambda price: (
                price.datetime,
                price.code,
            ),
        )

    def aggregate_to_five_minutes(
        self,
        prices: list[StockPrice],
    ) -> list[StockPrice]:
        """株価を5分足へ集約する。"""

        return self.aggregate(
            prices=prices,
            interval_minutes=5,
        )

    @staticmethod
    def _calculate_bucket_start(
        traded_at: datetime,
        interval_minutes: int,
    ) -> datetime:
        """日時が所属する時間区間の開始時刻を返す。"""

        minute_offset = traded_at.minute % interval_minutes

        return traded_at.replace(
            minute=traded_at.minute - minute_offset,
            second=0,
            microsecond=0,
        )

    @staticmethod
    def expected_bucket_end(
        bucket_start: datetime,
        interval_minutes: int,
    ) -> datetime:
        """指定区間の終了直前に相当する時刻を返す。"""

        if interval_minutes <= 0:
            raise ValueError("集約間隔は0より大きい必要があります。")

        return bucket_start + timedelta(minutes=interval_minutes) - timedelta(seconds=1)
