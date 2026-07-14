"""moomoo OpenDからトヨタの5分足を取得して確認する。"""

from app.market.moomoo_downloader import (
    MoomooHistoricalDownloader,
)


def main() -> None:
    """7203の過去5分足を取得して先頭と末尾を表示する。"""

    downloader = MoomooHistoricalDownloader()

    prices = downloader.download(
        code="JP.7203",
        start="2026-07-13",
        end="2026-07-13",
    )

    print("=" * 50)
    print("moomoo 5-minute kline download successful")
    print("=" * 50)
    print(f"records: {len(prices)}")

    if not prices:
        print("指定期間のデータはありません。")
        return

    print("first:")
    print(prices[0])

    print("last:")
    print(prices[-1])


if __name__ == "__main__":
    main()
