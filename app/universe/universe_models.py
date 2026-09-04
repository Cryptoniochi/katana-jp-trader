"""全市場ユニバースの共通モデル。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ListedSymbol:
    """上場銘柄マスターの1銘柄。"""

    code: str
    name: str
    market: str
    security_type: str
    trading_unit: int
    listed_date: date | None
    delisted_date: date | None
    is_active: bool
    source: str
    updated_at: datetime

    def __post_init__(self) -> None:
        normalized = self.code.strip()
        if not normalized:
            raise ValueError("銘柄コードを指定してください。")
        if self.trading_unit <= 0:
            raise ValueError("売買単位は0より大きい必要があります。")
        if self.updated_at.tzinfo is None:
            raise ValueError("更新日時にはタイムゾーンが必要です。")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["listed_date"] = (
            self.listed_date.isoformat()
            if self.listed_date is not None else None
        )
        payload["delisted_date"] = (
            self.delisted_date.isoformat()
            if self.delisted_date is not None else None
        )
        payload["updated_at"] = self.updated_at.isoformat()
        return payload


@dataclass(frozen=True, slots=True)
class UniverseScreeningSettings:
    """全市場一次スクリーニング設定。"""

    allowed_markets: tuple[str, ...] = ("Prime", "Standard", "Growth")
    allowed_security_types: tuple[str, ...] = ("common_stock",)
    maximum_purchase_amount: float = 950_000.0
    minimum_latest_price: float = 100.0
    maximum_latest_price: float = 9_500.0
    minimum_average_turnover: float = 5_000_000.0
    minimum_average_volume: float = 5_000.0
    maximum_symbols: int = 300
    maximum_data_age_days: int = 45
    lookback_days: int = 20

    def __post_init__(self) -> None:
        if self.maximum_purchase_amount <= 0:
            raise ValueError("最大購入金額は0より大きい必要があります。")
        if self.minimum_latest_price < 0:
            raise ValueError("最低株価は0以上です。")
        if self.maximum_latest_price <= self.minimum_latest_price:
            raise ValueError("最高株価は最低株価より大きい必要があります。")
        if self.maximum_symbols <= 0:
            raise ValueError("最大候補数は0より大きい必要があります。")
        if self.lookback_days <= 0:
            raise ValueError("参照日数は0より大きい必要があります。")


@dataclass(frozen=True, slots=True)
class UniverseScreeningCandidate:
    """一次スクリーニング結果。"""

    code: str
    name: str
    market: str
    security_type: str
    trading_unit: int
    latest_price: float
    purchase_amount: float
    average_volume: float
    average_turnover: float
    latest_trading_date: date
    score: float
    exclusion_reasons: tuple[str, ...]
    selected: bool
    atr_ratio: float = 0.0
    volume_ratio: float = 0.0
    return_5d: float = 0.0
    breakout_ratio: float = 0.0
    range_expansion_ratio: float = 0.0
    gap_ratio: float = 0.0
    close_position_ratio: float = 0.5
    opportunity_score: float = 0.0
    liquidity_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["latest_trading_date"] = self.latest_trading_date.isoformat()
        return payload


@dataclass(frozen=True, slots=True)
class UniverseScreeningReport:
    """一次スクリーニング全体の結果。"""

    generated_at: datetime
    universe_count: int
    evaluated_count: int
    eligible_count: int
    selected_count: int
    settings: UniverseScreeningSettings
    selected: tuple[UniverseScreeningCandidate, ...]
    excluded: tuple[UniverseScreeningCandidate, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "universe_count": self.universe_count,
            "evaluated_count": self.evaluated_count,
            "eligible_count": self.eligible_count,
            "selected_count": self.selected_count,
            "settings": asdict(self.settings),
            "selected": [item.to_dict() for item in self.selected],
            "excluded": [item.to_dict() for item in self.excluded],
        }
