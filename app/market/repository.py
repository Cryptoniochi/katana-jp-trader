"""株価データの保存処理。"""

import sqlite3
from pathlib import Path

from app.market.models import StockPrice


class StockRepository:
    """株価データをSQLiteへ保存するリポジトリ。"""

    def __init__(self, database_path: Path) -> None:
        """データベースの保存先を受け取る。"""
        self.database_path = database_path

    def save(self, stock: StockPrice) -> None:
        """株価データを1件保存する。"""

        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO stock_prices (
                    code,
                    traded_at,
                    open,
                    high,
                    low,
                    close,
                    volume
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, traded_at)
                DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume
                """,
                (
                    stock.code,
                    stock.datetime.isoformat(),
                    stock.open,
                    stock.high,
                    stock.low,
                    stock.close,
                    stock.volume,
                ),
            )

            connection.commit()

    def count(self) -> int:
        """保存されている株価データの件数を返す。"""

        with sqlite3.connect(self.database_path) as connection:
            result = connection.execute(
                "SELECT COUNT(*) FROM stock_prices"
            ).fetchone()

        if result is None:
            return 0

        return int(result[0])