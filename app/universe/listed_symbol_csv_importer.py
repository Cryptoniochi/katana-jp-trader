"""CSVから上場銘柄マスターを取り込む。"""

from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from app.universe.listed_symbol_repository import (
    ListedSymbolRepository,
)
from app.universe.universe_models import (
    ListedSymbol,
)


COLUMN_ALIASES = {
    "code": (
        "code",
        "銘柄コード",
        "コード",
    ),
    "name": (
        "name",
        "銘柄名",
        "会社名",
    ),
    "market": (
        "market",
        "市場・商品区分",
        "市場区分",
    ),
    "security_type": (
        "security_type",
        "商品区分",
        "証券種別",
    ),
    "trading_unit": (
        "trading_unit",
        "単元株数",
        "売買単位",
    ),
    "listed_date": (
        "listed_date",
        "上場日",
    ),
    "delisted_date": (
        "delisted_date",
        "上場廃止日",
    ),
    "is_active": (
        "is_active",
        "上場中",
    ),
}


class ListedSymbolCsvImporter:
    """任意の列名を正規化して銘柄マスターへ保存する。"""

    def __init__(
        self,
        *,
        database_path: Path,
        source_name: str = "csv",
        now_provider: Callable[
            [],
            datetime,
        ] | None = None,
    ) -> None:
        self.repository = ListedSymbolRepository(
            database_path
        )
        self.source_name = source_name
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(
                timezone.utc
            )
        )

    def import_file(
        self,
        csv_path: Path,
    ) -> tuple[ListedSymbol, ...]:
        path = Path(csv_path)

        if not path.exists():
            raise FileNotFoundError(path)

        rows = self._read_rows(path)
        symbols = tuple(
            self._to_symbol(row)
            for row in rows
        )
        self.repository.upsert_many(symbols)
        return symbols

    def _read_rows(
        self,
        path: Path,
    ) -> tuple[dict[str, str], ...]:
        last_error: Exception | None = None

        for encoding in (
            "utf-8-sig",
            "cp932",
            "utf-8",
        ):
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
                        for row in csv.DictReader(
                            handle
                        )
                    )
            except UnicodeError as error:
                last_error = error

        raise UnicodeError(
            "CSVの文字コードを判定できません。"
        ) from last_error

    def _to_symbol(
        self,
        row: dict[str, str],
    ) -> ListedSymbol:
        code = self._value(row, "code")
        name = self._value(row, "name")
        market = self._normalize_market(
            self._value(row, "market")
        )
        security_type = (
            self._normalize_security_type(
                self._value(
                    row,
                    "security_type",
                    default="common_stock",
                )
            )
        )
        trading_unit = int(
            self._value(
                row,
                "trading_unit",
                default="100",
            )
        )

        active_text = self._value(
            row,
            "is_active",
            default="true",
        ).lower()
        is_active = active_text not in {
            "0",
            "false",
            "no",
            "inactive",
            "上場廃止",
        }

        return ListedSymbol(
            code=code,
            name=name,
            market=market,
            security_type=security_type,
            trading_unit=trading_unit,
            listed_date=self._parse_date(
                self._value(
                    row,
                    "listed_date",
                    default="",
                )
            ),
            delisted_date=self._parse_date(
                self._value(
                    row,
                    "delisted_date",
                    default="",
                )
            ),
            is_active=is_active,
            source=self.source_name,
            updated_at=self.now_provider(),
        )

    @staticmethod
    def _value(
        row: dict[str, str],
        logical_name: str,
        *,
        default: str | None = None,
    ) -> str:
        for alias in COLUMN_ALIASES[
            logical_name
        ]:
            if alias in row and row[alias] != "":
                return row[alias]

        if default is not None:
            return default

        raise ValueError(
            f"必須列がありません: {logical_name}"
        )

    @staticmethod
    def _normalize_market(
        value: str,
    ) -> str:
        normalized = value.strip()

        if "プライム" in normalized:
            return "Prime"
        if "スタンダード" in normalized:
            return "Standard"
        if "グロース" in normalized:
            return "Growth"

        return normalized

    @staticmethod
    def _normalize_security_type(
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        common_markers = (
            "common",
            "普通株",
            "内国株",
        )

        if any(
            marker in normalized
            for marker in common_markers
        ):
            return "common_stock"

        if "reit" in normalized:
            return "reit"
        if "etf" in normalized:
            return "etf"

        return normalized or "common_stock"

    @staticmethod
    def _parse_date(
        value: str,
    ) -> date | None:
        cleaned = value.strip()

        if not cleaned:
            return None

        for separator in (
            "/",
            ".",
        ):
            cleaned = cleaned.replace(
                separator,
                "-",
            )

        return date.fromisoformat(cleaned)
