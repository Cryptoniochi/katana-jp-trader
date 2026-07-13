"""市場データの取得・保存を統括するサービス。"""

from dataclasses import dataclass
from pathlib import Path

from app.market.csv_repository import CsvStockRepository
from app.market.downloader import DummyDownloader
from app.market.repository import StockRepository


@dataclass(frozen=True, slots=True)
class MarketImportResult:
    """市場データ取込処理の結果。"""

    downloaded_count: int
    database_count: int
    latest_csv_path: Path | None


class MarketDataService:
    """市場データの取得と保存を実行する。"""

    def __init__(
        self,
        downloader: DummyDownloader,
        sqlite_repository: StockRepository,
        csv_repository: CsvStockRepository,
    ) -> None:
        """必要な構成要素を受け取る。"""

        self.downloader = downloader
        self.sqlite_repository = sqlite_repository
        self.csv_repository = csv_repository

    def import_prices(self) -> MarketImportResult:
        """株価を取得し、SQLiteとCSVへ保存する。"""

        prices = self.downloader.download()
        latest_csv_path: Path | None = None

        for price in prices:
            self.sqlite_repository.save(price)
            latest_csv_path = self.csv_repository.save(price)

        return MarketImportResult(
            downloaded_count=len(prices),
            database_count=self.sqlite_repository.count(),
            latest_csv_path=latest_csv_path,
        )
