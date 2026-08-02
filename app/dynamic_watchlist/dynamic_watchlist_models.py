"""Dynamic Watchlistのデータモデル。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class DynamicWatchlistSettings:
    """Dynamic Watchlistの選定条件。"""

    capital_limit: float = 1_000_000.0
    purchase_budget: float = 950_000.0
    trading_unit: int = 100
    maximum_symbols: int = 50
    minimum_symbols: int = 10
    minimum_history_days: int = 20
    fallback_minimum_history_days: int = 3
    minimum_average_turnover: float = 50_000_000.0
    fallback_minimum_average_turnover: float = 5_000_000.0
    minimum_average_volume: float = 50_000.0
    fallback_minimum_average_volume: float = 5_000.0
    maximum_data_age_days: int = 10
    fallback_maximum_data_age_days: int = 45
    learning_feedback_enabled: bool = True
    learning_total_score_weight: float = 1.0
    learning_strategy_score_weight: float = 0.25

    def __post_init__(self) -> None:
        if self.capital_limit <= 0:
            raise ValueError(
                "運用資金上限は0より大きい必要があります。"
            )
        if not 0 < self.purchase_budget <= self.capital_limit:
            raise ValueError(
                "購入予算は0より大きく、"
                "運用資金上限以下である必要があります。"
            )
        if self.trading_unit <= 0:
            raise ValueError(
                "売買単位は0より大きい必要があります。"
            )
        if self.maximum_symbols <= 0:
            raise ValueError(
                "最大銘柄数は0より大きい必要があります。"
            )
        if not 0 < self.minimum_symbols <= self.maximum_symbols:
            raise ValueError(
                "最低銘柄数は1以上かつ最大銘柄数以下です。"
            )
        if self.minimum_history_days < 20:
            raise ValueError(
                "厳格モードの最低履歴日数は20日以上必要です。"
            )
        if not 1 <= self.fallback_minimum_history_days <= self.minimum_history_days:
            raise ValueError(
                "フォールバック最低履歴日数は1以上かつ"
                "厳格モード以下である必要があります。"
            )
        if self.fallback_minimum_average_turnover < 0:
            raise ValueError(
                "フォールバック最低売買代金は0以上です。"
            )
        if self.fallback_minimum_average_volume < 0:
            raise ValueError(
                "フォールバック最低出来高は0以上です。"
            )
        if self.learning_total_score_weight < 0:
            raise ValueError(
                "学習総合スコア係数は0以上です。"
            )
        if self.learning_strategy_score_weight < 0:
            raise ValueError(
                "学習戦略スコア係数は0以上です。"
            )
        if self.fallback_maximum_data_age_days < self.maximum_data_age_days:
            raise ValueError(
                "フォールバック最大データ経過日数は"
                "厳格モード以上である必要があります。"
            )


@dataclass(frozen=True, slots=True)
class DynamicWatchlistCandidate:
    """1銘柄の選定結果。"""

    code: str
    latest_date: date
    latest_price: float
    trading_unit: int
    purchase_amount: float
    history_days: int
    average_volume_20d: float
    average_turnover_20d: float
    volume_ratio: float
    return_20d: float
    breakout_ratio: float
    atr_ratio: float
    gap_ratio: float
    vwap_distance_ratio: float
    close_position_ratio: float
    pullback_depth_ratio: float
    breakout_score: float
    momentum_score: float
    liquidity_score: float
    volume_score: float
    volatility_score: float
    gap_score: float
    vwap_score: float
    orb_score: float
    pullback_score: float
    high_breakout_score: float
    technical_score: float
    historical_score: float
    historical_trade_count: int
    learning_applied: bool
    learned_preferred_strategy: str | None
    total_score: float
    rating_tier: str
    preferred_strategy: str
    selection_tier: str
    selected: bool
    exclusion_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["latest_date"] = self.latest_date.isoformat()
        payload["exclusion_reasons"] = list(
            self.exclusion_reasons
        )
        return payload


@dataclass(frozen=True, slots=True)
class DynamicWatchlistResult:
    """Dynamic Watchlist生成結果。"""

    generated_at: datetime
    target_date: date
    settings: DynamicWatchlistSettings
    selected: tuple[DynamicWatchlistCandidate, ...]
    evaluated_count: int
    eligible_count: int
    applied: bool
    watchlist_path: str | None
    backup_path: str | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "target_date": self.target_date.isoformat(),
            "settings": asdict(self.settings),
            "selected": [
                candidate.to_dict()
                for candidate in self.selected
            ],
            "evaluated_count": self.evaluated_count,
            "eligible_count": self.eligible_count,
            "applied": self.applied,
            "watchlist_path": self.watchlist_path,
            "backup_path": self.backup_path,
            "message": self.message,
        }
