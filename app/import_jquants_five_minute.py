"""J-Quantsの1分足を5分足へ変換してSQLiteへ保存する。"""

from app.database import initialize_database
from app.logger import create_logger
from app.market.bar_aggregator import StockPriceAggregator
from app.market.bar_repository import MarketBarRepository
from app.market.jquants_downloader import (
    JQuantsDownloadError,
    JQuantsMinuteDownloader,
)
from app.settings import settings

TARGET_CODE = "7203"
TARGET_DATE = "2026-07-13"
INTERVAL_MINUTES = 5
DATA_SOURCE = "jquants"


def main() -> None:
    """トヨタの5分足を取得・変換・保存する。"""

    print("=" * 50)
    print(f"{settings.app_name} - J-Quants 5-Minute Import")
    print(f"Version : {settings.version}")
    print("=" * 50)

    settings.create_directories()
    initialize_database(settings.database_path)

    logger = create_logger(settings.logs_dir)

    downloader = JQuantsMinuteDownloader()
    aggregator = StockPriceAggregator()
    repository = MarketBarRepository(settings.database_path)

    try:
        minute_prices = downloader.download(
            code=TARGET_CODE,
            date=TARGET_DATE,
        )

        five_minute_prices = aggregator.aggregate_to_five_minutes(minute_prices)

        saved_count = repository.save_all(
            prices=five_minute_prices,
            interval_minutes=INTERVAL_MINUTES,
            data_source=DATA_SOURCE,
        )

    except (
        JQuantsDownloadError,
        ValueError,
    ) as error:
        logger.error(
            "J-Quantsの5分足取込に失敗しました: %s",
            error,
        )
        return

    database_count = repository.count(
        code=TARGET_CODE,
        interval_minutes=INTERVAL_MINUTES,
    )

    logger.info(
        "J-Quants 1分足を取得しました。code=%s date=%s records=%d",
        TARGET_CODE,
        TARGET_DATE,
        len(minute_prices),
    )

    logger.info(
        "5分足へ集約しました。records=%d",
        len(five_minute_prices),
    )

    logger.info(
        "SQLiteへ保存しました。processed=%d database_count=%d",
        saved_count,
        database_count,
    )

    if five_minute_prices:
        logger.info(
            "保存範囲: first=%s last=%s",
            five_minute_prices[0].datetime,
            five_minute_prices[-1].datetime,
        )

    logger.info("Import completed.")


if __name__ == "__main__":
    main()
