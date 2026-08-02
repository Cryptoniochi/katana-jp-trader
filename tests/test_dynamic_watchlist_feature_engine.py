"""DynamicWatchlistFeatureEngineのテスト。"""

from app.dynamic_watchlist.dynamic_watchlist_feature_engine import (
    DynamicWatchlistFeatureEngine,
    DynamicWatchlistFeatureInput,
)


def test_feature_engine_returns_bounded_score() -> None:
    scores = DynamicWatchlistFeatureEngine().evaluate(
        DynamicWatchlistFeatureInput(
            average_turnover_20d=1_000_000_000,
            volume_ratio=2.0,
            atr_ratio=0.035,
            gap_ratio=0.02,
            vwap_distance_ratio=0.005,
            return_20d=0.12,
            breakout_ratio=0.02,
            close_position_ratio=0.8,
            pullback_depth_ratio=0.03,
        )
    )

    assert 0 <= scores.total_score <= 100
    assert scores.tier in {"A+", "A", "B", "C"}
    assert scores.preferred_strategy in {
        "orb",
        "pullback",
        "high-breakout",
    }


def test_strong_gap_and_volume_favor_orb() -> None:
    scores = DynamicWatchlistFeatureEngine().evaluate(
        DynamicWatchlistFeatureInput(
            average_turnover_20d=2_000_000_000,
            volume_ratio=2.5,
            atr_ratio=0.04,
            gap_ratio=0.02,
            vwap_distance_ratio=0.01,
            return_20d=0.02,
            breakout_ratio=0.0,
            close_position_ratio=0.9,
            pullback_depth_ratio=0.0,
        )
    )

    assert scores.orb_score >= scores.high_breakout_score


def test_trend_and_pullback_favor_pullback() -> None:
    scores = DynamicWatchlistFeatureEngine().evaluate(
        DynamicWatchlistFeatureInput(
            average_turnover_20d=500_000_000,
            volume_ratio=1.1,
            atr_ratio=0.03,
            gap_ratio=0.0,
            vwap_distance_ratio=0.005,
            return_20d=0.18,
            breakout_ratio=-0.02,
            close_position_ratio=0.55,
            pullback_depth_ratio=0.035,
        )
    )

    assert scores.pullback_score >= scores.high_breakout_score
