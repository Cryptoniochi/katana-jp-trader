"""全市場日足データ取込モデル。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class UniverseDailyBar:
    """全市場スクリーニング用の日足。"""

    code: str
    trading_date: date
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int
    data_source: str

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("銘柄コードを指定してください。")
        if self.volume < 0:
            raise ValueError("出来高は0以上です。")
        if min(
            self.open_price,
            self.high_price,
            self.low_price,
            self.close_price,
        ) < 0:
            raise ValueError("価格は0以上です。")
        if self.high_price < self.low_price:
            raise ValueError("高値は安値以上です。")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["trading_date"] = self.trading_date.isoformat()
        return payload


@dataclass(frozen=True, slots=True)
class UniverseDailyImportResult:
    """日足CSV取込結果。"""

    generated_at: datetime
    input_row_count: int
    imported_row_count: int
    skipped_row_count: int
    symbol_count: int
    earliest_date: date | None
    latest_date: date | None
    source_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "input_row_count": self.input_row_count,
            "imported_row_count": self.imported_row_count,
            "skipped_row_count": self.skipped_row_count,
            "symbol_count": self.symbol_count,
            "earliest_date": (
                self.earliest_date.isoformat()
                if self.earliest_date else None
            ),
            "latest_date": (
                self.latest_date.isoformat()
                if self.latest_date else None
            ),
            "source_name": self.source_name,
        }
