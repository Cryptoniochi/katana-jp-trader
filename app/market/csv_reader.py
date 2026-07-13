"""株価CSVの読み込み処理。"""

import csv
from datetime import datetime
from pathlib import Path

from app.market.models import StockPrice


class CsvStockReader:
    """CSVファイルから株価データを読み込む。"""

    def read(self, file_path: Path) -> list[StockPrice]:
        """CSVファイルを読み込み、株価データの一覧を返す。"""

        if not file_path.exists():
            raise FileNotFoundError(f"CSVファイルが見つかりません: {file_path}")

        prices: list[StockPrice] = []

        with file_path.open(
            mode="r",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:
            reader = csv.DictReader(csv_file)

            for row in reader:
                prices.append(
                    StockPrice(
                        code=row["code"],
                        datetime=datetime.fromisoformat(row["traded_at"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(row["volume"]),
                    )
                )

        return prices
