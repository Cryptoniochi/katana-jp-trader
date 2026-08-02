"""全市場日足CSVを既存market_barsへ取り込む。"""

from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from app.universe.universe_daily_bar_models import (
    UniverseDailyBar,
    UniverseDailyImportResult,
)
from app.universe.universe_daily_bar_repository import (
    UniverseDailyBarRepository,
)


ALIASES = {
    "code": ("code", "銘柄コード", "コード"),
    "date": ("date", "trading_date", "日付", "取引日"),
    "open": ("open", "始値"),
    "high": ("high", "高値"),
    "low": ("low", "安値"),
    "close": ("close", "終値"),
    "volume": ("volume", "出来高"),
}


class UniverseDailyBarCsvImporter:
    """約4,000銘柄の日足CSVをバッチ取込する。"""

    def __init__(
        self,
        *,
        database_path: Path,
        source_name: str = "universe-daily-csv",
        batch_size: int = 10_000,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_sizeは0より大きい必要があります。")

        self.repository = UniverseDailyBarRepository(database_path)
        self.source_name = source_name.strip()
        self.batch_size = batch_size
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def import_file(
        self,
        csv_path: Path,
        *,
        skip_invalid_rows: bool = False,
    ) -> UniverseDailyImportResult:
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(path)

        imported = 0
        skipped = 0
        input_rows = 0
        symbols: set[str] = set()
        dates: list[date] = []
        batch: list[UniverseDailyBar] = []

        for row_number, row in enumerate(
            self._read_rows(path),
            start=2,
        ):
            input_rows += 1
            try:
                bar = self._to_bar(row)
            except (ValueError, KeyError) as error:
                if not skip_invalid_rows:
                    raise ValueError(
                        f"日足CSVの{row_number}行目が不正です。"
                    ) from error
                skipped += 1
                continue

            batch.append(bar)
            symbols.add(bar.code)
            dates.append(bar.trading_date)

            if len(batch) >= self.batch_size:
                imported += self.repository.upsert_many(
                    tuple(batch)
                )
                batch.clear()

        if batch:
            imported += self.repository.upsert_many(
                tuple(batch)
            )

        now = self.now_provider()
        if now.tzinfo is None:
            raise ValueError("現在日時にはタイムゾーンが必要です。")

        return UniverseDailyImportResult(
            generated_at=now.astimezone(timezone.utc),
            input_row_count=input_rows,
            imported_row_count=imported,
            skipped_row_count=skipped,
            symbol_count=len(symbols),
            earliest_date=min(dates) if dates else None,
            latest_date=max(dates) if dates else None,
            source_name=self.source_name,
        )

    def _read_rows(
        self,
        path: Path,
    ) -> tuple[dict[str, str], ...]:
        last_error = None

        for encoding in ("utf-8-sig", "cp932", "utf-8"):
            try:
                with path.open(
                    "r",
                    encoding=encoding,
                    newline="",
                ) as handle:
                    return tuple(
                        {
                            str(key).strip(): (
                                str(value).strip()
                                if value is not None
                                else ""
                            )
                            for key, value in row.items()
                        }
                        for row in csv.DictReader(handle)
                    )
            except UnicodeError as error:
                last_error = error

        raise UnicodeError(
            "CSVの文字コードを判定できません。"
        ) from last_error

    def _to_bar(
        self,
        row: dict[str, str],
    ) -> UniverseDailyBar:
        return UniverseDailyBar(
            code=self._value(row, "code"),
            trading_date=self._parse_date(
                self._value(row, "date")
            ),
            open_price=float(self._value(row, "open")),
            high_price=float(self._value(row, "high")),
            low_price=float(self._value(row, "low")),
            close_price=float(self._value(row, "close")),
            volume=int(float(self._value(row, "volume"))),
            data_source=self.source_name,
        )

    @staticmethod
    def _value(
        row: dict[str, str],
        logical_name: str,
    ) -> str:
        for alias in ALIASES[logical_name]:
            value = row.get(alias, "")
            if value != "":
                return value
        raise KeyError(logical_name)

    @staticmethod
    def _parse_date(value: str) -> date:
        normalized = (
            value.strip()
            .replace("/", "-")
            .replace(".", "-")
        )
        if len(normalized) == 8 and "-" not in normalized:
            normalized = (
                f"{normalized[:4]}-"
                f"{normalized[4:6]}-"
                f"{normalized[6:]}"
            )
        return date.fromisoformat(normalized)
