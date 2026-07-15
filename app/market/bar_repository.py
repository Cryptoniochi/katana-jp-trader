"""時間足データをSQLiteへ保存・取得する処理。"""

import sqlite3
from datetime import datetime
from pathlib import Path

from app.market.models import StockPrice


class MarketBarRepository:
    """StockPrice形式の時間足をSQLiteへ保存する。"""

    def __init__(
        self,
        database_path: Path,
    ) -> None:
        """データベースの保存先を設定する。"""

        self.database_path = database_path

    def save_all(
        self,
        prices: list[StockPrice],
        interval_minutes: int,
        data_source: str,
    ) -> int:
        """複数の時間足を一括保存し、処理件数を返す。"""

        self._validate_common_arguments(
            interval_minutes=interval_minutes,
            data_source=data_source,
        )

        if not prices:
            return 0

        rows = [
            (
                price.code,
                price.datetime.isoformat(),
                interval_minutes,
                price.open,
                price.high,
                price.low,
                price.close,
                price.volume,
                data_source,
            )
            for price in prices
        ]

        with sqlite3.connect(self.database_path) as connection:
            connection.executemany(
                """
                INSERT INTO market_bars (
                    code,
                    traded_at,
                    interval_minutes,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    data_source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                    code,
                    traded_at,
                    interval_minutes
                )
                DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    data_source = excluded.data_source,
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )

            connection.commit()

        return len(rows)

    def read(
        self,
        code: str,
        interval_minutes: int,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[StockPrice]:
        """銘柄・時間軸・期間を指定して時間足を返す。"""

        normalized_code = self._normalize_code(code)
        self._validate_interval(interval_minutes)

        if start_at is not None and end_at is not None and start_at > end_at:
            raise ValueError("開始日時は終了日時以前にしてください。")

        conditions = [
            "code = ?",
            "interval_minutes = ?",
        ]
        parameters: list[object] = [
            normalized_code,
            interval_minutes,
        ]

        if start_at is not None:
            conditions.append("traded_at >= ?")
            parameters.append(start_at.isoformat())

        if end_at is not None:
            conditions.append("traded_at <= ?")
            parameters.append(end_at.isoformat())

        where_clause = " AND ".join(conditions)

        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    code,
                    traded_at,
                    open,
                    high,
                    low,
                    close,
                    volume
                FROM market_bars
                WHERE {where_clause}
                ORDER BY traded_at, code
                """,
                parameters,
            ).fetchall()

        return [
            StockPrice(
                code=str(row[0]),
                datetime=datetime.fromisoformat(str(row[1])),
                open=float(row[2]),
                high=float(row[3]),
                low=float(row[4]),
                close=float(row[5]),
                volume=int(row[6]),
            )
            for row in rows
        ]

    def latest_datetime(
        self,
        code: str,
        interval_minutes: int,
    ) -> datetime | None:
        """指定銘柄・時間軸の最新保存日時を返す。"""

        normalized_code = self._normalize_code(code)
        self._validate_interval(interval_minutes)

        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT MAX(traded_at)
                FROM market_bars
                WHERE code = ?
                  AND interval_minutes = ?
                """,
                (
                    normalized_code,
                    interval_minutes,
                ),
            ).fetchone()

        if row is None or row[0] is None:
            return None

        return datetime.fromisoformat(str(row[0]))

    def earliest_datetime(
        self,
        code: str,
        interval_minutes: int,
    ) -> datetime | None:
        """指定銘柄・時間軸の最古保存日時を返す。"""

        normalized_code = self._normalize_code(code)
        self._validate_interval(interval_minutes)

        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT MIN(traded_at)
                FROM market_bars
                WHERE code = ?
                  AND interval_minutes = ?
                """,
                (
                    normalized_code,
                    interval_minutes,
                ),
            ).fetchone()

        if row is None or row[0] is None:
            return None

        return datetime.fromisoformat(str(row[0]))

    def count(
        self,
        code: str | None = None,
        interval_minutes: int | None = None,
    ) -> int:
        """条件に一致する時間足の件数を返す。"""

        conditions: list[str] = []
        parameters: list[object] = []

        if code is not None:
            conditions.append("code = ?")
            parameters.append(self._normalize_code(code))

        if interval_minutes is not None:
            self._validate_interval(interval_minutes)

            conditions.append("interval_minutes = ?")
            parameters.append(interval_minutes)

        where_clause = ""

        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        with sqlite3.connect(self.database_path) as connection:
            result = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM market_bars
                {where_clause}
                """,
                parameters,
            ).fetchone()

        if result is None:
            return 0

        return int(result[0])

    @staticmethod
    def _normalize_code(
        code: str,
    ) -> str:
        """銘柄コードを検証して前後の空白を除く。"""

        normalized_code = code.strip()

        if not normalized_code:
            raise ValueError("銘柄コードを指定してください。")

        return normalized_code

    @staticmethod
    def _validate_interval(
        interval_minutes: int,
    ) -> None:
        """時間足の間隔を検証する。"""

        if interval_minutes <= 0:
            raise ValueError("時間足の間隔は0より大きい必要があります。")

    @classmethod
    def _validate_common_arguments(
        cls,
        interval_minutes: int,
        data_source: str,
    ) -> None:
        """保存時の共通引数を検証する。"""

        cls._validate_interval(interval_minutes)

        if not data_source.strip():
            raise ValueError("データソースを指定してください。")
