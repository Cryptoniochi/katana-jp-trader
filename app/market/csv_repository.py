"""株価データのCSV保存処理。"""

import csv
from pathlib import Path

from app.market.models import StockPrice


class CsvStockRepository:
    """株価データを日付別CSVへ保存するリポジトリ。"""

    def __init__(self, csv_directory: Path) -> None:
        """CSV保存先フォルダを受け取る。"""
        self.csv_directory = csv_directory
        self.csv_directory.mkdir(parents=True, exist_ok=True)

    def save(self, stock: StockPrice) -> Path:
        """株価データを1件CSVへ保存し、ファイルパスを返す。"""

        file_name = f"{stock.datetime.date().isoformat()}.csv"
        file_path = self.csv_directory / file_name

        file_exists = file_path.exists()

        with file_path.open(
            mode="a",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:
            writer = csv.writer(csv_file)

            if not file_exists:
                writer.writerow(
                    [
                        "code",
                        "traded_at",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                    ]
                )

            writer.writerow(
                [
                    stock.code,
                    stock.datetime.isoformat(),
                    stock.open,
                    stock.high,
                    stock.low,
                    stock.close,
                    stock.volume,
                ]
            )

        return file_path