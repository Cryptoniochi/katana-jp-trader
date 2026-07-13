"""株価データの集計処理。"""

from dataclasses import dataclass

from app.market.models import StockPrice


@dataclass(frozen=True, slots=True)
class StockSummary:
    """株価データの集計結果。"""

    record_count: int
    latest_close: float
    total_volume: int
    highest_price: float
    lowest_price: float


def summarize_prices(prices: list[StockPrice]) -> StockSummary:
    """株価データを集計する。"""

    if not prices:
        raise ValueError("集計対象の株価データがありません。")

    latest_price = max(
        prices,
        key=lambda price: price.datetime,
    )

    return StockSummary(
        record_count=len(prices),
        latest_close=latest_price.close,
        total_volume=sum(price.volume for price in prices),
        highest_price=max(price.high for price in prices),
        lowest_price=min(price.low for price in prices),
    )