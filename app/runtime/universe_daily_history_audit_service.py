"""全市場の日次履歴蓄積を検証する監査サービス。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable


@dataclass(frozen=True, slots=True)
class UniverseDailyHistoryAuditResult:
    """1営業日分の全市場日足蓄積状況。"""

    generated_at: datetime
    trading_date: date
    active_universe_count: int
    collected_count: int
    missing_count: int
    terminal_skipped_count: int
    unexplained_missing_count: int
    collection_ratio: float
    effective_coverage_ratio: float
    completed: bool
    symbols_with_1_day: int
    symbols_with_5_days: int
    symbols_with_10_days: int
    symbols_with_20_days: int
    fallback_count: int
    developing_count: int
    strict_count: int
    missing_codes: tuple[str, ...]
    unexplained_missing_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "trading_date": self.trading_date.isoformat(),
            "active_universe_count": self.active_universe_count,
            "collected_count": self.collected_count,
            "missing_count": self.missing_count,
            "terminal_skipped_count": self.terminal_skipped_count,
            "unexplained_missing_count": (
                self.unexplained_missing_count
            ),
            "collection_ratio": round(
                self.collection_ratio,
                6,
            ),
            "effective_coverage_ratio": round(
                self.effective_coverage_ratio,
                6,
            ),
            "completed": self.completed,
            "symbols_with_1_day": self.symbols_with_1_day,
            "symbols_with_5_days": self.symbols_with_5_days,
            "symbols_with_10_days": self.symbols_with_10_days,
            "symbols_with_20_days": self.symbols_with_20_days,
            "fallback_count": self.fallback_count,
            "developing_count": self.developing_count,
            "strict_count": self.strict_count,
            "missing_codes": list(self.missing_codes),
            "unexplained_missing_codes": list(
                self.unexplained_missing_codes
            ),
        }


class UniverseDailyHistoryAuditService:
    """listed_symbolsとmarket_barsを突合して日次蓄積を監査する。"""

    def __init__(
        self,
        *,
        database_path: Path,
        minimum_effective_coverage_ratio: float = 0.99,
        terminal_skip_path: Path = Path(
            "reports/universe/bootstrap_unavailable.json"
        ),
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        if not 0 < minimum_effective_coverage_ratio <= 1:
            raise ValueError(
                "minimum_effective_coverage_ratioは"
                "0より大きく1以下である必要があります。"
            )

        self.database_path = Path(database_path)
        self.minimum_effective_coverage_ratio = float(
            minimum_effective_coverage_ratio
        )
        self.terminal_skip_path = Path(
            terminal_skip_path
        )
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def audit(
        self,
        *,
        trading_date: date,
    ) -> UniverseDailyHistoryAuditResult:
        """指定日の全市場日足蓄積と履歴成熟度を返す。"""

        active_codes = self._load_active_codes()
        if not active_codes:
            raise RuntimeError(
                "listed_symbolsに有効な国内普通株がありません。"
            )

        collected_codes = self._load_collected_codes(
            trading_date=trading_date
        )
        terminal_codes = self._load_terminal_codes(
            trading_date=trading_date
        )

        active_set = set(active_codes)
        collected_in_universe = (
            collected_codes & active_set
        )
        terminal_in_universe = (
            terminal_codes & active_set
        )

        missing = active_set - collected_in_universe
        unexplained_missing = (
            missing - terminal_in_universe
        )

        active_count = len(active_set)
        collected_count = len(
            collected_in_universe
        )
        terminal_count = len(
            terminal_in_universe & missing
        )
        effective_count = (
            collected_count + terminal_count
        )

        collection_ratio = (
            collected_count / active_count
        )
        effective_ratio = (
            effective_count / active_count
        )

        history_counts = self._load_history_counts(
            active_codes=active_codes,
            up_to_date=trading_date,
        )
        values = [
            history_counts.get(code, 0)
            for code in active_codes
        ]

        return UniverseDailyHistoryAuditResult(
            generated_at=self._current_time(),
            trading_date=trading_date,
            active_universe_count=active_count,
            collected_count=collected_count,
            missing_count=len(missing),
            terminal_skipped_count=terminal_count,
            unexplained_missing_count=len(
                unexplained_missing
            ),
            collection_ratio=collection_ratio,
            effective_coverage_ratio=effective_ratio,
            completed=(
                effective_ratio
                >= self.minimum_effective_coverage_ratio
                and not unexplained_missing
            ),
            symbols_with_1_day=sum(
                value >= 1
                for value in values
            ),
            symbols_with_5_days=sum(
                value >= 5
                for value in values
            ),
            symbols_with_10_days=sum(
                value >= 10
                for value in values
            ),
            symbols_with_20_days=sum(
                value >= 20
                for value in values
            ),
            fallback_count=sum(
                1 <= value < 10
                for value in values
            ),
            developing_count=sum(
                10 <= value < 20
                for value in values
            ),
            strict_count=sum(
                value >= 20
                for value in values
            ),
            missing_codes=tuple(
                sorted(missing)
            ),
            unexplained_missing_codes=tuple(
                sorted(unexplained_missing)
            ),
        )

    def _load_active_codes(
        self,
    ) -> tuple[str, ...]:
        if not self.database_path.exists():
            raise FileNotFoundError(
                f"Database not found: {self.database_path}"
            )

        with sqlite3.connect(
            self.database_path
        ) as connection:
            table = connection.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'listed_symbols'
                """
            ).fetchone()
            if table is None:
                raise RuntimeError(
                    "listed_symbols table is missing."
                )

            rows = connection.execute(
                """
                SELECT code
                FROM listed_symbols
                WHERE is_active = 1
                  AND market IN (
                    'Prime',
                    'Standard',
                    'Growth'
                  )
                  AND security_type = 'common_stock'
                ORDER BY code
                """
            ).fetchall()

        return tuple(
            str(row[0]).strip().upper()
            for row in rows
            if row and row[0]
        )

    def _load_collected_codes(
        self,
        *,
        trading_date: date,
    ) -> set[str]:
        with sqlite3.connect(
            self.database_path
        ) as connection:
            table = connection.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'market_bars'
                """
            ).fetchone()
            if table is None:
                return set()

            rows = connection.execute(
                """
                SELECT DISTINCT code
                FROM market_bars
                WHERE interval_minutes = 1440
                  AND substr(traded_at, 1, 10) = ?
                """,
                (
                    trading_date.isoformat(),
                ),
            ).fetchall()

        return {
            str(row[0]).strip().upper()
            for row in rows
            if row and row[0]
        }

    def _load_history_counts(
        self,
        *,
        active_codes: tuple[str, ...],
        up_to_date: date,
    ) -> dict[str, int]:
        placeholders = ",".join(
            "?"
            for _ in active_codes
        )

        with sqlite3.connect(
            self.database_path
        ) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    code,
                    COUNT(
                        DISTINCT substr(
                            traded_at,
                            1,
                            10
                        )
                    ) AS history_days
                FROM market_bars
                WHERE interval_minutes = 1440
                  AND code IN ({placeholders})
                  AND substr(traded_at, 1, 10) <= ?
                GROUP BY code
                """,
                (
                    *active_codes,
                    up_to_date.isoformat(),
                ),
            ).fetchall()

        return {
            str(row[0]).strip().upper(): int(
                row[1] or 0
            )
            for row in rows
        }

    def _load_terminal_codes(
        self,
        *,
        trading_date: date,
    ) -> set[str]:
        if not self.terminal_skip_path.exists():
            return set()

        import json

        try:
            payload = json.loads(
                self.terminal_skip_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            return set()

        if not isinstance(payload, dict):
            return set()

        if str(
            payload.get("trading_date") or ""
        ) != trading_date.isoformat():
            return set()

        entries = payload.get("entries")
        if not isinstance(entries, dict):
            return set()

        return {
            str(code).strip().upper()
            for code in entries
            if str(code).strip()
        }

    def _current_time(self) -> datetime:
        value = self.now_provider()
        if value.tzinfo is None:
            raise ValueError(
                "now_provider must return "
                "timezone-aware datetime."
            )
        return value.astimezone(
            timezone.utc
        )
