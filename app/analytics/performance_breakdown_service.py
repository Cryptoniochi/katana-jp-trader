"""Trade Journalを曜日・時間帯・銘柄・決済理由で集計する。"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.analytics.performance_breakdown_models import (
    PerformanceBreakdownPayload,
    PerformanceBreakdownRow,
)


class PerformanceBreakdownAnalyzer:
    """Trade Journalの多角的な成績分析を行う。"""

    WEEKDAY_LABELS = (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    )

    def __init__(
        self,
        database_path: Path,
        *,
        now_provider: Callable[[], datetime] | None = None,
        symbol_limit: int = 20,
    ) -> None:
        if symbol_limit <= 0:
            raise ValueError(
                "銘柄表示件数は0より大きい必要があります。"
            )

        self.database_path = Path(database_path)
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self.symbol_limit = symbol_limit

    def analyze(
        self,
    ) -> PerformanceBreakdownPayload:
        """全完了トレードを4軸で集計する。"""

        generated_at = self._current_time()

        if not self.database_path.exists():
            return self._empty_payload(
                generated_at
            )

        with sqlite3.connect(
            self.database_path
        ) as connection:
            if not self._table_exists(
                connection,
                "trade_journal",
            ):
                return self._empty_payload(
                    generated_at
                )

            rows = connection.execute(
                """
                SELECT
                    code,
                    entry_at,
                    exit_reason,
                    realized_profit_loss,
                    return_rate
                FROM trade_journal
                ORDER BY exit_at ASC, id ASC
                """
            ).fetchall()

        normalized = tuple(
            {
                "code": str(row[0]),
                "entry_at": self._parse_datetime(
                    str(row[1])
                ),
                "exit_reason": (
                    str(row[2]).strip()
                    if row[2] is not None
                    and str(row[2]).strip()
                    else "unknown"
                ),
                "profit_loss": float(row[3]),
                "return_rate": float(row[4]),
            }
            for row in rows
        )

        weekday = self._aggregate(
            normalized,
            key_provider=lambda item: str(
                item["entry_at"].weekday()
            ),
            label_provider=lambda key: (
                self.WEEKDAY_LABELS[int(key)]
            ),
            sort_key=lambda item: int(item.key),
        )
        entry_hour = self._aggregate(
            normalized,
            key_provider=lambda item: (
                f"{item['entry_at'].hour:02d}"
            ),
            label_provider=lambda key: (
                f"{key}:00–{key}:59"
            ),
            sort_key=lambda item: item.key,
        )
        symbol = self._aggregate(
            normalized,
            key_provider=lambda item: str(
                item["code"]
            ),
            label_provider=lambda key: key,
            sort_key=lambda item: (
                -item.net_profit_loss,
                -item.trade_count,
                item.key,
            ),
        )[: self.symbol_limit]
        exit_reason = self._aggregate(
            normalized,
            key_provider=lambda item: str(
                item["exit_reason"]
            ),
            label_provider=lambda key: key,
            sort_key=lambda item: (
                -item.trade_count,
                -item.net_profit_loss,
                item.key,
            ),
        )

        return PerformanceBreakdownPayload(
            generated_at=generated_at,
            weekday=weekday,
            entry_hour=entry_hour,
            symbol=symbol,
            exit_reason=exit_reason,
        )

    def _aggregate(
        self,
        rows: tuple[dict[str, object], ...],
        *,
        key_provider,
        label_provider,
        sort_key,
    ) -> tuple[PerformanceBreakdownRow, ...]:
        grouped: dict[
            str,
            list[dict[str, object]],
        ] = defaultdict(list)

        for row in rows:
            grouped[
                key_provider(row)
            ].append(row)

        result = []

        for key, values in grouped.items():
            profits = [
                float(item["profit_loss"])
                for item in values
                if float(item["profit_loss"]) > 0
            ]
            losses = [
                float(item["profit_loss"])
                for item in values
                if float(item["profit_loss"]) < 0
            ]
            trade_count = len(values)
            gross_profit = sum(profits)
            gross_loss = sum(losses)
            profit_factor = (
                gross_profit / abs(gross_loss)
                if gross_loss < 0
                else (
                    float("inf")
                    if gross_profit > 0
                    else None
                )
            )

            result.append(
                PerformanceBreakdownRow(
                    key=key,
                    label=label_provider(key),
                    trade_count=trade_count,
                    win_count=len(profits),
                    loss_count=len(losses),
                    win_rate=(
                        len(profits) / trade_count
                        if trade_count > 0
                        else None
                    ),
                    net_profit_loss=sum(
                        float(item["profit_loss"])
                        for item in values
                    ),
                    gross_profit=gross_profit,
                    gross_loss=gross_loss,
                    profit_factor=profit_factor,
                    average_profit_loss=(
                        sum(
                            float(item["profit_loss"])
                            for item in values
                        )
                        / trade_count
                        if trade_count > 0
                        else None
                    ),
                    average_return_rate=(
                        sum(
                            float(item["return_rate"])
                            for item in values
                        )
                        / trade_count
                        if trade_count > 0
                        else None
                    ),
                )
            )

        return tuple(
            sorted(
                result,
                key=sort_key,
            )
        )

    @staticmethod
    def _table_exists(
        connection: sqlite3.Connection,
        table_name: str,
    ) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    def _current_time(self) -> datetime:
        value = self.now_provider()

        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return value.astimezone(timezone.utc)

    @staticmethod
    def _parse_datetime(
        value: str,
    ) -> datetime:
        parsed = datetime.fromisoformat(value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _empty_payload(
        generated_at: datetime,
    ) -> PerformanceBreakdownPayload:
        return PerformanceBreakdownPayload(
            generated_at=generated_at,
            weekday=(),
            entry_hour=(),
            symbol=(),
            exit_reason=(),
        )
