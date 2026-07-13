"""Project KATANAの起動処理。"""

from app.database import initialize_database
from app.logger import create_logger
from app.market.downloader import DummyDownloader
from app.market.repository import StockRepository
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

    downloader = DummyDownloader()
    repository = StockRepository(settings.database_path)

    prices = downloader.download()

    for price in prices:
        repository.save(price)
        logger.info(
            "株価を保存しました。code=%s close=%.2f volume=%d",
            price.code,
            price.close,
            price.volume,
        )

    logger.info("Downloaded %d records.", len(prices))
    logger.info(
        "データベース内の株価件数: %d",
        repository.count(),
    )
    logger.info("Startup completed.")


if __name__ == "__main__":
    main()