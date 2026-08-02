"""Dynamic Watchlistの特徴量・戦略適性モデル。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DynamicWatchlistFeatureScores:
    """銘柄ごとの特徴量と戦略適性スコア。"""

    liquidity_score: float
    relative_volume_score: float
    volatility_score: float
    gap_score: float
    vwap_score: float
    orb_score: float
    pullback_score: float
    high_breakout_score: float
    total_score: float
    tier: str
    preferred_strategy: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
