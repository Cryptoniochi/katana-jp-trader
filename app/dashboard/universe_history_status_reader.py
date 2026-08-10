"""Dashboard用Universe History Coverage Reader。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


@dataclass(frozen=True, slots=True)
class UniverseHistoryCoverage:
    generated_at: datetime
    active_universe_count: int
    symbols_with_1_day: int
    symbols_with_5_days: int
    symbols_with_10_days: int
    symbols_with_20_days: int
    fallback_count: int
    developing_count: int
    strict_count: int
    no_history_count: int
    latest_market_data_date: str | None

    def to_dict(self) -> dict[str, object]:
        total = self.active_universe_count

        def ratio(count: int) -> float:
            if total <= 0:
                return 0.0
            return round(count / total, 6)

        return {
            "available": True,
            "generated_at": self.generated_at.isoformat(),
            "active_universe_count": total,
            "symbols_with_1_day": self.symbols_with_1_day,
            "symbols_with_5_days": self.symbols_with_5_days,
            "symbols_with_10_days": self.symbols_with_10_days,
            "symbols_with_20_days": self.symbols_with_20_days,
            "fallback_count": self.fallback_count,
            "developing_count": self.developing_count,
            "strict_count": self.strict_count,
            "no_history_count": self.no_history_count,
            "latest_market_data_date": self.latest_market_data_date,
            "coverage_1_day": ratio(self.symbols_with_1_day),
            "coverage_5_days": ratio(self.symbols_with_5_days),
            "coverage_10_days": ratio(self.symbols_with_10_days),
            "coverage_20_days": ratio(self.symbols_with_20_days),
        }


class UniverseHistoryStatusReader:
    """listed_symbolsとmarket_barsから履歴成熟度を集計する。"""

    def __init__(
        self,
        database_path: Path = Path("data/katana.db"),
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def read(self) -> dict[str, object]:
        if not self.database_path.exists():
            return self._unavailable("Database not found.")

        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row

            if not self._table_exists(connection, "listed_symbols"):
                return self._unavailable(
                    "listed_symbols table is missing."
                )

            if not self._table_exists(connection, "market_bars"):
                return self._unavailable(
                    "market_bars table is missing."
                )

            active_codes = tuple(
                str(row["code"]).strip().upper()
                for row in connection.execute(
                    """
                    SELECT code
                    FROM listed_symbols
                    WHERE is_active = 1
                      AND market IN ('Prime', 'Standard', 'Growth')
                      AND security_type = 'common_stock'
                    ORDER BY code
                    """
                ).fetchall()
                if row["code"]
            )

            if not active_codes:
                return UniverseHistoryCoverage(
                    generated_at=self._current_time(),
                    active_universe_count=0,
                    symbols_with_1_day=0,
                    symbols_with_5_days=0,
                    symbols_with_10_days=0,
                    symbols_with_20_days=0,
                    fallback_count=0,
                    developing_count=0,
                    strict_count=0,
                    no_history_count=0,
                    latest_market_data_date=None,
                ).to_dict()

            placeholders = ",".join("?" for _ in active_codes)
            rows = connection.execute(
                f"""
                SELECT
                    code,
                    COUNT(DISTINCT substr(traded_at, 1, 10)) AS history_days,
                    MAX(substr(traded_at, 1, 10)) AS latest_date
                FROM market_bars
                WHERE interval_minutes = 1440
                  AND code IN ({placeholders})
                GROUP BY code
                """,
                active_codes,
            ).fetchall()

        history_days = {
            str(row["code"]).strip().upper(): int(
                row["history_days"] or 0
            )
            for row in rows
        }
        latest_dates = [
            str(row["latest_date"])
            for row in rows
            if row["latest_date"]
        ]
        counts = [
            history_days.get(code, 0)
            for code in active_codes
        ]

        return UniverseHistoryCoverage(
            generated_at=self._current_time(),
            active_universe_count=len(active_codes),
            symbols_with_1_day=sum(v >= 1 for v in counts),
            symbols_with_5_days=sum(v >= 5 for v in counts),
            symbols_with_10_days=sum(v >= 10 for v in counts),
            symbols_with_20_days=sum(v >= 20 for v in counts),
            fallback_count=sum(1 <= v < 10 for v in counts),
            developing_count=sum(10 <= v < 20 for v in counts),
            strict_count=sum(v >= 20 for v in counts),
            no_history_count=sum(v == 0 for v in counts),
            latest_market_data_date=(
                max(latest_dates)
                if latest_dates
                else None
            ),
        ).to_dict()

    @staticmethod
    def _table_exists(
        connection: sqlite3.Connection,
        table_name: str,
    ) -> bool:
        return (
            connection.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = ?
                """,
                (table_name,),
            ).fetchone()
            is not None
        )

    def _unavailable(
        self,
        message: str,
    ) -> dict[str, object]:
        return {
            "available": False,
            "generated_at": self._current_time().isoformat(),
            "active_universe_count": 0,
            "symbols_with_1_day": 0,
            "symbols_with_5_days": 0,
            "symbols_with_10_days": 0,
            "symbols_with_20_days": 0,
            "fallback_count": 0,
            "developing_count": 0,
            "strict_count": 0,
            "no_history_count": 0,
            "latest_market_data_date": None,
            "coverage_1_day": 0.0,
            "coverage_5_days": 0.0,
            "coverage_10_days": 0.0,
            "coverage_20_days": 0.0,
            "message": message,
        }

    def _current_time(self) -> datetime:
        value = self.now_provider()
        if value.tzinfo is None:
            raise ValueError(
                "now_provider must return timezone-aware datetime."
            )
        return value.astimezone(timezone.utc)
