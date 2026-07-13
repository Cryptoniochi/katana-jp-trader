"""複数の株価CSVを読み込む処理。"""

from pathlib import Path

from app.market.csv_reader import CsvStockReader
from app.market.models import StockPrice


class HistoricalCsvReader:
    """フォルダ内の複数CSVから株価履歴を読み込む。"""

    def __init__(self, csv_reader: CsvStockReader | None = None) -> None:
        """単一CSV用リーダーを受け取る。"""

        self.csv_reader = csv_reader or CsvStockReader()

    def read_directory(
        self,
        directory: Path,
        code: str | None = None,
    ) -> list[StockPrice]:
        """フォルダ内の全CSVを読み込み、時系列順で返す。"""

        if not directory.exists():
            raise FileNotFoundError(f"履歴データフォルダが見つかりません: {directory}")

        if not directory.is_dir():
            raise NotADirectoryError(f"フォルダではありません: {directory}")

        csv_paths = sorted(directory.glob("*.csv"))

        if not csv_paths:
            raise FileNotFoundError(f"CSVファイルがありません: {directory}")

        prices: list[StockPrice] = []

        for csv_path in csv_paths:
            prices.extend(self.csv_reader.read(csv_path))

        if code is not None:
            prices = [price for price in prices if price.code == code]

        unique_prices: dict[
            tuple[str, object],
            StockPrice,
        ] = {}

        for price in prices:
            key = (price.code, price.datetime)
            unique_prices[key] = price

        return sorted(
            unique_prices.values(),
            key=lambda price: (
                price.datetime,
                price.code,
            ),
        )
