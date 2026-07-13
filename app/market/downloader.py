"""データ取得"""

from datetime import datetime

from app.market.models import StockPrice


class DummyDownloader:
    def download(self) -> list[StockPrice]:

        return [
            StockPrice(
                code="7203",
                datetime=datetime.now(),
                open=3500,
                high=3520,
                low=3490,
                close=3515,
                volume=1234567,
            )
        ]
