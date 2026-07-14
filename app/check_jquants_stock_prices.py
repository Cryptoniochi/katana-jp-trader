"""J-Quantsの1分足をStockPriceへ変換して確認する。"""

from app.market.jquants_downloader import (
    JQuantsMinuteDownloader,
)


def main() -> None:
    """トヨタの1分足を取得して先頭と末尾を表示する。"""

    downloader = JQuantsMinuteDownloader()

    prices = downloader.download(
        code="7203",
        date="2026-07-13",
    )

    print("=" * 50)
    print("J-Quants StockPrice conversion successful")
    print("=" * 50)
    print(f"records: {len(prices)}")

    if not prices:
        print("指定日の分足データは0件でした。")
        return

    print("first:")
    print(prices[0])

    print("last:")
    print(prices[-1])


if __name__ == "__main__":
    main()
