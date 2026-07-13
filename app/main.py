"""Project KATANAの起動処理。"""

from app.database import initialize_database
from app.logger import create_logger
from app.market.csv_reader import CsvStockReader
from app.market.csv_repository import CsvStockRepository
from app.market.downloader import DummyDownloader
from app.market.repository import StockRepository
from app.market.service import MarketDataService
from app.market.summary import summarize_prices
from app.settings import settings


def main() -> None:
    """アプリケーションを起動する。"""

    print("=" * 50)
    print(settings.app_name)
    print(f"Version : {settings.version}")
    print("=" * 50)

    settings.create_directories()
    logger = create_logger(settings.logs_dir)

    logger.info("Project KATANAを起動します。")
    logger.info("設定を読み込みました。")

    initialize_database(settings.database_path)
    logger.info("データベースを初期化しました。")

    service = MarketDataService(
        downloader=DummyDownloader(),
        sqlite_repository=StockRepository(settings.database_path),
        csv_repository=CsvStockRepository(settings.csv_dir),
    )

    result = service.import_prices()

    logger.info(
        "市場データを取り込みました。downloaded=%d database_count=%d",
        result.downloaded_count,
        result.database_count,
    )

    if result.latest_csv_path is not None:
        logger.info(
            "CSVへ保存しました。path=%s",
            result.latest_csv_path,
        )

        csv_reader = CsvStockReader()
        saved_prices = csv_reader.read(result.latest_csv_path)
        summary = summarize_prices(saved_prices)

        logger.info(
            "CSV集計: records=%d latest_close=%.2f "
            "total_volume=%d highest=%.2f lowest=%.2f",
            summary.record_count,
            summary.latest_close,
            summary.total_volume,
            summary.highest_price,
            summary.lowest_price,
        )

    logger.info("Startup completed.")


if __name__ == "__main__":
    main()