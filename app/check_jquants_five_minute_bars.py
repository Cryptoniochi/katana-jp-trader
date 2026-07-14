"""J-Quantsの1分足を5分足へ集約して確認する。"""

from app.market.bar_aggregator import StockPriceAggregator
from app.market.jquants_downloader import (
    JQuantsMinuteDownloader,
)


def main() -> None:
    """トヨタの1分足を取得し、5分足へ集約する。"""

    downloader = JQuantsMinuteDownloader()
    aggregator = StockPriceAggregator()

    minute_prices = downloader.download(
        code="7203",
        date="2026-07-13",
    )

    five_minute_prices = aggregator.aggregate_to_five_minutes(minute_prices)

    print("=" * 50)
    print("J-Quants five-minute aggregation successful")
    print("=" * 50)
    print(f"one-minute records: {len(minute_prices)}")
    print(f"five-minute records: {len(five_minute_prices)}")

    if not five_minute_prices:
        print("5分足データは0件でした。")
        return

    print("first:")
    print(five_minute_prices[0])

    print("last:")
    print(five_minute_prices[-1])

    print("morning session last bars:")

    morning_bars = [price for price in five_minute_prices if price.datetime.hour < 12]

    for price in morning_bars[-3:]:
        print(price)

    print("afternoon session first bars:")

    afternoon_bars = [
        price for price in five_minute_prices if price.datetime.hour >= 12
    ]

    for price in afternoon_bars[:3]:
        print(price)


if __name__ == "__main__":
    main()
