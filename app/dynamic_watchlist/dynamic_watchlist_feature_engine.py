"""Dynamic Watchlistの特徴量スコアリング。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean

from app.dynamic_watchlist.dynamic_watchlist_feature_models import (
    DynamicWatchlistFeatureScores,
)


@dataclass(frozen=True, slots=True)
class DynamicWatchlistFeatureInput:
    """Feature Engineへ渡す正規化済み特徴量。"""

    average_turnover_20d: float
    volume_ratio: float
    atr_ratio: float
    gap_ratio: float
    vwap_distance_ratio: float
    return_20d: float
    breakout_ratio: float
    close_position_ratio: float
    pullback_depth_ratio: float


class DynamicWatchlistFeatureEngine:
    """特徴量から100点満点の銘柄スコアを作る。"""

    def evaluate(
        self,
        feature: DynamicWatchlistFeatureInput,
    ) -> DynamicWatchlistFeatureScores:
        liquidity = self._log_scale(
            feature.average_turnover_20d,
            lower=5_000_000.0,
            upper=5_000_000_000.0,
            maximum=20.0,
        )
        relative_volume = self._scale(
            feature.volume_ratio,
            lower=0.5,
            upper=3.0,
            maximum=15.0,
        )
        volatility = self._bell_score(
            feature.atr_ratio,
            ideal=0.035,
            tolerance=0.03,
            maximum=15.0,
        )
        gap = self._bell_score(
            abs(feature.gap_ratio),
            ideal=0.02,
            tolerance=0.03,
            maximum=10.0,
        )
        vwap = self._bell_score(
            abs(feature.vwap_distance_ratio),
            ideal=0.005,
            tolerance=0.025,
            maximum=10.0,
        )

        orb = self._orb_score(feature)
        pullback = self._pullback_score(feature)
        high_breakout = self._high_breakout_score(
            feature
        )

        total = round(
            liquidity
            + relative_volume
            + volatility
            + gap
            + vwap
            + orb
            + pullback
            + high_breakout,
            4,
        )
        tier = self._resolve_tier(total)
        preferred_strategy = self._preferred_strategy(
            orb_score=orb,
            pullback_score=pullback,
            high_breakout_score=high_breakout,
        )

        return DynamicWatchlistFeatureScores(
            liquidity_score=round(liquidity, 4),
            relative_volume_score=round(
                relative_volume,
                4,
            ),
            volatility_score=round(volatility, 4),
            gap_score=round(gap, 4),
            vwap_score=round(vwap, 4),
            orb_score=round(orb, 4),
            pullback_score=round(pullback, 4),
            high_breakout_score=round(
                high_breakout,
                4,
            ),
            total_score=total,
            tier=tier,
            preferred_strategy=preferred_strategy,
        )

    def _orb_score(
        self,
        feature: DynamicWatchlistFeatureInput,
    ) -> float:
        score = fmean(
            [
                self._scale(
                    feature.volume_ratio,
                    lower=0.8,
                    upper=2.5,
                    maximum=5.0,
                ),
                self._bell_score(
                    abs(feature.gap_ratio),
                    ideal=0.02,
                    tolerance=0.03,
                    maximum=3.0,
                ),
                self._scale(
                    feature.close_position_ratio,
                    lower=0.45,
                    upper=0.95,
                    maximum=2.0,
                ),
            ]
        ) * 3.0
        return min(10.0, score)

    def _pullback_score(
        self,
        feature: DynamicWatchlistFeatureInput,
    ) -> float:
        trend = self._scale(
            feature.return_20d,
            lower=-0.05,
            upper=0.20,
            maximum=4.0,
        )
        pullback = self._bell_score(
            feature.pullback_depth_ratio,
            ideal=0.035,
            tolerance=0.04,
            maximum=4.0,
        )
        vwap = self._bell_score(
            abs(feature.vwap_distance_ratio),
            ideal=0.005,
            tolerance=0.02,
            maximum=2.0,
        )
        return min(10.0, trend + pullback + vwap)

    def _high_breakout_score(
        self,
        feature: DynamicWatchlistFeatureInput,
    ) -> float:
        breakout = self._scale(
            feature.breakout_ratio,
            lower=-0.05,
            upper=0.05,
            maximum=3.0,
        )
        trend = self._scale(
            feature.return_20d,
            lower=-0.05,
            upper=0.25,
            maximum=1.0,
        )
        volume = self._scale(
            feature.volume_ratio,
            lower=0.8,
            upper=3.0,
            maximum=1.0,
        )
        return min(5.0, breakout + trend + volume)

    @staticmethod
    def _preferred_strategy(
        *,
        orb_score: float,
        pullback_score: float,
        high_breakout_score: float,
    ) -> str:
        scores = {
            "orb": orb_score,
            "pullback": pullback_score,
            "high-breakout": high_breakout_score,
        }
        return max(
            scores,
            key=lambda name: (
                scores[name],
                name,
            ),
        )

    @staticmethod
    def _resolve_tier(
        total_score: float,
    ) -> str:
        if total_score >= 80:
            return "A+"
        if total_score >= 65:
            return "A"
        if total_score >= 50:
            return "B"
        return "C"

    @staticmethod
    def _scale(
        value: float,
        *,
        lower: float,
        upper: float,
        maximum: float,
    ) -> float:
        if upper <= lower:
            return 0.0
        ratio = (value - lower) / (upper - lower)
        return max(
            0.0,
            min(maximum, ratio * maximum),
        )

    @staticmethod
    def _log_scale(
        value: float,
        *,
        lower: float,
        upper: float,
        maximum: float,
    ) -> float:
        if value <= 0 or upper <= lower:
            return 0.0
        return DynamicWatchlistFeatureEngine._scale(
            math.log10(value),
            lower=math.log10(lower),
            upper=math.log10(upper),
            maximum=maximum,
        )

    @staticmethod
    def _bell_score(
        value: float,
        *,
        ideal: float,
        tolerance: float,
        maximum: float,
    ) -> float:
        if tolerance <= 0:
            return 0.0
        distance = abs(value - ideal)
        return max(
            0.0,
            maximum * (
                1.0 - distance / tolerance
            ),
        )
