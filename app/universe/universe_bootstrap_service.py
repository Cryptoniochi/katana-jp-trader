"""全市場Universeの日足Bootstrapを段階実行する。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Protocol

from app.universe.kabu_station_universe_daily_collector import (
    UniverseDailyCollectionResult,
)
from app.universe.listed_symbol_repository import ListedSymbolRepository


class UniverseDailyCollectorProtocol(Protocol):
    def collect(
        self,
        *,
        trading_date: date,
        codes: tuple[str, ...] | list[str],
    ) -> UniverseDailyCollectionResult:
        ...


@dataclass(frozen=True, slots=True)
class UniverseBootstrapResult:
    generated_at: datetime
    trading_date: date
    universe_count: int
    already_collected_count: int
    attempted_count: int
    collected_count: int
    remaining_count: int
    retryable_remaining_count: int
    terminal_skipped_count: int
    coverage_ratio: float
    completed: bool
    selected_codes: tuple[str, ...]
    failed_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "trading_date": self.trading_date.isoformat(),
            "universe_count": self.universe_count,
            "already_collected_count": self.already_collected_count,
            "attempted_count": self.attempted_count,
            "collected_count": self.collected_count,
            "remaining_count": self.remaining_count,
            "retryable_remaining_count": self.retryable_remaining_count,
            "terminal_skipped_count": self.terminal_skipped_count,
            "coverage_ratio": round(self.coverage_ratio, 6),
            "completed": self.completed,
            "selected_codes": list(self.selected_codes),
            "failed_codes": list(self.failed_codes),
        }


class UniverseBootstrapService:
    """listed_symbolsをmarket_barsへ段階的にBootstrapする。"""

    def __init__(
        self,
        *,
        database_path: Path,
        collector: UniverseDailyCollectorProtocol,
        maximum_symbols_per_run: int = 300,
        minimum_completion_ratio: float = 0.99,
        unavailable_path: Path = Path(
            "reports/universe/bootstrap_unavailable.json"
        ),
        allowed_markets: tuple[str, ...] = (
            "Prime",
            "Standard",
            "Growth",
        ),
        allowed_security_types: tuple[str, ...] = (
            "common_stock",
        ),
        now_provider=None,
    ) -> None:
        if maximum_symbols_per_run <= 0:
            raise ValueError(
                "maximum_symbols_per_runは1以上である必要があります。"
            )
        if not 0 < minimum_completion_ratio <= 1:
            raise ValueError(
                "minimum_completion_ratioは0より大きく1以下である必要があります。"
            )

        self.database_path = Path(database_path)
        self.collector = collector
        self.maximum_symbols_per_run = int(maximum_symbols_per_run)
        self.minimum_completion_ratio = float(minimum_completion_ratio)
        self.unavailable_path = Path(unavailable_path)
        self.allowed_markets = allowed_markets
        self.allowed_security_types = allowed_security_types
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def run_once(self, *, trading_date: date) -> UniverseBootstrapResult:
        universe = ListedSymbolRepository(self.database_path).load_active(
            allowed_markets=self.allowed_markets,
            allowed_security_types=self.allowed_security_types,
        )
        universe_codes = tuple(item.code for item in universe)
        if not universe_codes:
            raise RuntimeError(
                "listed_symbolsにBootstrap対象銘柄がありません。"
            )

        unavailable = self._load_unavailable(trading_date=trading_date)
        terminal_codes = set(unavailable)
        collected_before = self._load_collected_codes(
            trading_date=trading_date
        )

        pending = tuple(
            code
            for code in universe_codes
            if code not in collected_before and code not in terminal_codes
        )
        selected = pending[: self.maximum_symbols_per_run]

        if not selected:
            return self._build_result(
                trading_date=trading_date,
                universe_codes=universe_codes,
                collected_before=collected_before,
                attempted_count=0,
                collected_count=0,
                selected_codes=(),
                failed_codes=(),
                terminal_codes=terminal_codes,
            )

        collection = self.collector.collect(
            trading_date=trading_date,
            codes=selected,
        )

        newly_terminal = self._extract_terminal_unavailable(collection)
        if newly_terminal:
            now = self._current_time()
            for code, reason in newly_terminal.items():
                existing = unavailable.get(code, {})
                unavailable[code] = {
                    "reason": reason,
                    "first_recorded_at": existing.get(
                        "first_recorded_at", now.isoformat()
                    ),
                    "last_recorded_at": now.isoformat(),
                }
            self._write_unavailable(
                trading_date=trading_date,
                entries=unavailable,
            )

        collected_after = self._load_collected_codes(
            trading_date=trading_date
        )
        terminal_codes = set(unavailable)
        successful_selected = {
            code for code in selected if code in collected_after
        }
        failed_codes = tuple(
            code for code in selected if code not in successful_selected
        )

        return self._build_result(
            trading_date=trading_date,
            universe_codes=universe_codes,
            collected_before=collected_before,
            attempted_count=len(selected),
            collected_count=len(successful_selected),
            selected_codes=tuple(selected),
            failed_codes=failed_codes,
            terminal_codes=terminal_codes,
        )

    def _build_result(
        self,
        *,
        trading_date: date,
        universe_codes: tuple[str, ...],
        collected_before: set[str],
        attempted_count: int,
        collected_count: int,
        selected_codes: tuple[str, ...],
        failed_codes: tuple[str, ...],
        terminal_codes: set[str],
    ) -> UniverseBootstrapResult:
        collected_after = self._load_collected_codes(
            trading_date=trading_date
        )
        remaining_codes = {
            code for code in universe_codes if code not in collected_after
        }
        retryable_remaining = {
            code for code in remaining_codes if code not in terminal_codes
        }
        terminal_in_universe = {
            code
            for code in terminal_codes
            if code in remaining_codes and code in universe_codes
        }

        universe_count = len(universe_codes)
        covered_count = universe_count - len(retryable_remaining)
        coverage_ratio = (
            covered_count / universe_count if universe_count > 0 else 0.0
        )
        completed = (
            not retryable_remaining
            or coverage_ratio >= self.minimum_completion_ratio
        )

        return UniverseBootstrapResult(
            generated_at=self._current_time(),
            trading_date=trading_date,
            universe_count=universe_count,
            already_collected_count=len(
                collected_before.intersection(universe_codes)
            ),
            attempted_count=attempted_count,
            collected_count=collected_count,
            remaining_count=len(remaining_codes),
            retryable_remaining_count=len(retryable_remaining),
            terminal_skipped_count=len(terminal_in_universe),
            coverage_ratio=coverage_ratio,
            completed=completed,
            selected_codes=selected_codes,
            failed_codes=failed_codes,
        )

    @staticmethod
    def _extract_terminal_unavailable(
        collection: UniverseDailyCollectionResult,
    ) -> dict[str, str]:
        terminal: dict[str, str] = {}

        for item in collection.skips:
            terminal[item.code] = item.reason

        for item in collection.failures:
            message = item.message or ""
            if (
                "銘柄登録不可" in message
                or "registration failed" in message.lower()
                or "4001018" in message
            ):
                terminal[item.code] = message

        return terminal

    def _load_collected_codes(self, *, trading_date: date) -> set[str]:
        if not self.database_path.exists():
            return set()

        with sqlite3.connect(self.database_path) as connection:
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
                (trading_date.isoformat(),),
            ).fetchall()

        return {
            str(row[0]).strip().upper()
            for row in rows
            if row and row[0]
        }

    def _load_unavailable(
        self,
        *,
        trading_date: date,
    ) -> dict[str, dict[str, str]]:
        if not self.unavailable_path.exists():
            return {}

        try:
            payload = json.loads(
                self.unavailable_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}

        if not isinstance(payload, dict):
            return {}
        if str(payload.get("trading_date")) != trading_date.isoformat():
            return {}

        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, dict):
            return {}

        normalized: dict[str, dict[str, str]] = {}
        for code, value in raw_entries.items():
            if not isinstance(value, dict):
                continue
            normalized[str(code).strip().upper()] = {
                "reason": str(value.get("reason") or ""),
                "first_recorded_at": str(
                    value.get("first_recorded_at") or ""
                ),
                "last_recorded_at": str(
                    value.get("last_recorded_at") or ""
                ),
            }
        return normalized

    def _write_unavailable(
        self,
        *,
        trading_date: date,
        entries: dict[str, dict[str, str]],
    ) -> None:
        self.unavailable_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": self._current_time().isoformat(),
            "trading_date": trading_date.isoformat(),
            "count": len(entries),
            "entries": {
                code: entries[code] for code in sorted(entries)
            },
        }
        temporary = self.unavailable_path.with_suffix(
            self.unavailable_path.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.unavailable_path)

    def _current_time(self) -> datetime:
        value = self.now_provider()
        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )
        return value.astimezone(timezone.utc)
