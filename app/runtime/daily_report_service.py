"""Project KATANAの日次取引レポート生成サービス。"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

from app.runtime.daily_report_models import (
    DailyReportBreakdownRow,
    DailyReportStatus,
    DailyReportSummary,
    DailyTradingReport,
)


@dataclass(frozen=True, slots=True)
class DailyTradeRecord:
    """日次レポート集計に必要な最小取引データ。"""

    closed_at: datetime
    symbol: str
    strategy_name: str
    realized_profit_loss: float

    def __post_init__(self) -> None:
        if self.closed_at.tzinfo is None:
            raise ValueError(
                "決済日時にはタイムゾーンが必要です。"
            )

        if not self.symbol.strip():
            raise ValueError(
                "銘柄コードを指定してください。"
            )

        if not self.strategy_name.strip():
            raise ValueError(
                "戦略名を指定してください。"
            )


class SQLiteDailyTradeRepository:
    """SQLiteから日次決済取引を読み取るRepository。"""

    TABLE_CANDIDATES = (
        "trade_journal",
        "paper_trades",
        "trades",
    )
    CLOSED_AT_CANDIDATES = (
        "closed_at",
        "exited_at",
        "exit_at",
        "completed_at",
    )
    SYMBOL_CANDIDATES = (
        "symbol",
        "code",
        "stock_code",
    )
    STRATEGY_CANDIDATES = (
        "strategy_name",
        "strategy",
    )
    PNL_CANDIDATES = (
        "realized_profit_loss",
        "profit_loss",
        "pnl",
        "realized_pnl",
    )

    def __init__(
        self,
        database_path: Path,
    ) -> None:
        self.database_path = Path(database_path)

    def list_closed_trades(
        self,
        report_date: date,
    ) -> tuple[DailyTradeRecord, ...]:
        """対象日に決済された取引を返す。"""

        if not self.database_path.exists():
            raise FileNotFoundError(
                f"Database not found: {self.database_path}"
            )

        with sqlite3.connect(
            self.database_path,
            timeout=5.0,
        ) as connection:
            connection.row_factory = sqlite3.Row
            table = self._resolve_table(connection)
            columns = self._resolve_columns(
                connection,
                table,
            )

            start = datetime.combine(
                report_date,
                time.min,
                tzinfo=timezone.utc,
            )
            end = datetime.combine(
                report_date,
                time.max,
                tzinfo=timezone.utc,
            )

            query = (
                f'SELECT '
                f'"{columns["closed_at"]}" AS closed_at, '
                f'"{columns["symbol"]}" AS symbol, '
                f'"{columns["strategy"]}" AS strategy_name, '
                f'"{columns["pnl"]}" AS realized_profit_loss '
                f'FROM "{table}" '
                f'WHERE "{columns["closed_at"]}" >= ? '
                f'AND "{columns["closed_at"]}" <= ? '
                f'ORDER BY "{columns["closed_at"]}" ASC'
            )
            rows = connection.execute(
                query,
                (
                    start.isoformat(),
                    end.isoformat(),
                ),
            ).fetchall()

        return tuple(
            DailyTradeRecord(
                closed_at=self._parse_datetime(
                    row["closed_at"]
                ),
                symbol=str(row["symbol"]),
                strategy_name=str(
                    row["strategy_name"]
                ),
                realized_profit_loss=float(
                    row["realized_profit_loss"]
                ),
            )
            for row in rows
        )

    def _resolve_table(
        self,
        connection: sqlite3.Connection,
    ) -> str:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table'"
            ).fetchall()
        }

        for candidate in self.TABLE_CANDIDATES:
            if candidate in tables:
                return candidate

        raise RuntimeError(
            "日次レポート対象の取引テーブルが見つかりません。 "
            f"candidates={self.TABLE_CANDIDATES}"
        )

    def _resolve_columns(
        self,
        connection: sqlite3.Connection,
        table: str,
    ) -> dict[str, str]:
        columns = {
            str(row[1])
            for row in connection.execute(
                f'PRAGMA table_info("{table}")'
            ).fetchall()
        }

        return {
            "closed_at": self._pick_column(
                columns,
                self.CLOSED_AT_CANDIDATES,
            ),
            "symbol": self._pick_column(
                columns,
                self.SYMBOL_CANDIDATES,
            ),
            "strategy": self._pick_column(
                columns,
                self.STRATEGY_CANDIDATES,
            ),
            "pnl": self._pick_column(
                columns,
                self.PNL_CANDIDATES,
            ),
        }

    @staticmethod
    def _pick_column(
        available: set[str],
        candidates: Sequence[str],
    ) -> str:
        for candidate in candidates:
            if candidate in available:
                return candidate

        raise RuntimeError(
            "必要な取引列が見つかりません。 "
            f"candidates={tuple(candidates)} "
            f"available={tuple(sorted(available))}"
        )

    @staticmethod
    def _parse_datetime(
        value: object,
    ) -> datetime:
        parsed = datetime.fromisoformat(
            str(value)
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed


class DailyReportService:
    """取引一覧から日次レポートを生成する。"""

    def __init__(
        self,
        repository: SQLiteDailyTradeRepository,
    ) -> None:
        self.repository = repository

    def generate(
        self,
        *,
        report_date: date,
        generated_at: datetime | None = None,
        error_count: int = 0,
        recovery_count: int = 0,
        notes: Sequence[str] = (),
    ) -> DailyTradingReport:
        """対象日の取引を集計してレポートを返す。"""

        if error_count < 0:
            raise ValueError(
                "エラー件数は0以上である必要があります。"
            )

        if recovery_count < 0:
            raise ValueError(
                "復旧件数は0以上である必要があります。"
            )

        records = self.repository.list_closed_trades(
            report_date
        )
        summary = self._build_summary(records)
        strategy_breakdown = self._build_breakdown(
            records,
            key_getter=lambda record: (
                record.strategy_name
            ),
        )
        symbol_breakdown = self._build_breakdown(
            records,
            key_getter=lambda record: record.symbol,
        )

        normalized_notes = tuple(
            note.strip()
            for note in notes
            if note.strip()
        )
        status = self._resolve_status(
            trade_count=summary.trade_count,
            notes=normalized_notes,
        )

        return DailyTradingReport(
            report_date=report_date,
            generated_at=(
                generated_at
                if generated_at is not None
                else datetime.now(timezone.utc)
            ),
            status=status,
            summary=summary,
            strategy_breakdown=(
                strategy_breakdown
            ),
            symbol_breakdown=symbol_breakdown,
            error_count=error_count,
            recovery_count=recovery_count,
            notes=normalized_notes,
        )

    def generate_and_save(
        self,
        *,
        report_date: date,
        output_path: Path,
        generated_at: datetime | None = None,
        error_count: int = 0,
        recovery_count: int = 0,
        notes: Sequence[str] = (),
    ) -> DailyTradingReport:
        """日次レポートを生成してJSON保存する。"""

        report = self.generate(
            report_date=report_date,
            generated_at=generated_at,
            error_count=error_count,
            recovery_count=recovery_count,
            notes=notes,
        )
        target = Path(output_path)
        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        temporary = target.with_suffix(
            target.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(
                report.to_dict(),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(target)
        return report

    @staticmethod
    def _build_summary(
        records: Sequence[DailyTradeRecord],
    ) -> DailyReportSummary:
        values = [
            record.realized_profit_loss
            for record in records
        ]
        wins = [
            value
            for value in values
            if value > 0
        ]
        losses = [
            value
            for value in values
            if value < 0
        ]
        flats = [
            value
            for value in values
            if value == 0
        ]
        gross_profit = sum(wins)
        gross_loss = sum(losses)
        net_profit_loss = sum(values)
        trade_count = len(values)
        win_rate = (
            len(wins) / trade_count
            if trade_count > 0
            else None
        )
        profit_factor = (
            gross_profit / abs(gross_loss)
            if gross_loss < 0
            else (
                None
                if gross_profit == 0
                else gross_profit
            )
        )
        average_win = (
            gross_profit / len(wins)
            if wins
            else None
        )
        average_loss = (
            gross_loss / len(losses)
            if losses
            else None
        )

        return DailyReportSummary(
            trade_count=trade_count,
            win_count=len(wins),
            loss_count=len(losses),
            flat_count=len(flats),
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_profit_loss=net_profit_loss,
            win_rate=win_rate,
            profit_factor=profit_factor,
            average_win=average_win,
            average_loss=average_loss,
            maximum_drawdown=(
                DailyReportService
                ._calculate_maximum_drawdown(values)
            ),
        )

    @staticmethod
    def _build_breakdown(
        records: Sequence[DailyTradeRecord],
        *,
        key_getter,
    ) -> tuple[DailyReportBreakdownRow, ...]:
        grouped: dict[
            str,
            list[DailyTradeRecord],
        ] = defaultdict(list)

        for record in records:
            grouped[str(key_getter(record))].append(
                record
            )

        rows = []

        for key, group in grouped.items():
            summary = DailyReportService._build_summary(
                group
            )
            rows.append(
                DailyReportBreakdownRow(
                    key=key,
                    label=key,
                    trade_count=summary.trade_count,
                    net_profit_loss=(
                        summary.net_profit_loss
                    ),
                    win_rate=summary.win_rate,
                    profit_factor=summary.profit_factor,
                )
            )

        return tuple(
            sorted(
                rows,
                key=lambda row: (
                    -row.net_profit_loss,
                    row.key,
                ),
            )
        )

    @staticmethod
    def _calculate_maximum_drawdown(
        values: Iterable[float],
    ) -> float | None:
        cumulative = 0.0
        peak = 0.0
        maximum_drawdown = 0.0
        found = False

        for value in values:
            found = True
            cumulative += value
            peak = max(
                peak,
                cumulative,
            )
            maximum_drawdown = min(
                maximum_drawdown,
                cumulative - peak,
            )

        return (
            maximum_drawdown
            if found
            else None
        )

    @staticmethod
    def _resolve_status(
        *,
        trade_count: int,
        notes: Sequence[str],
    ) -> DailyReportStatus:
        if trade_count == 0:
            return DailyReportStatus.EMPTY

        if notes:
            return DailyReportStatus.PARTIAL

        return DailyReportStatus.COMPLETE
