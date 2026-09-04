"""Sprint 133: Dynamic Watchlist history maturity guard."""

from app.dynamic_watchlist.dynamic_watchlist_feature_engine import (
    DynamicWatchlistFeatureEngine,
    DynamicWatchlistFeatureInput,
)


def feature(history_days: int) -> DynamicWatchlistFeatureInput:
    return DynamicWatchlistFeatureInput(
        average_turnover_20d=1_000_000_000.0,
        volume_ratio=8.0,
        atr_ratio=0.08,
        gap_ratio=0.02,
        vwap_distance_ratio=0.01,
        return_20d=0.20,
        breakout_ratio=0.08,
        close_position_ratio=0.90,
        pullback_depth_ratio=0.035,
        history_days=history_days,
        full_history_days=20,
    )


def test_three_day_history_cannot_receive_mature_technical_score() -> None:
    engine = DynamicWatchlistFeatureEngine()
    sparse = engine.evaluate(feature(3))
    mature = engine.evaluate(feature(20))
    assert sparse.total_score < mature.total_score


def test_pullback_requires_full_history() -> None:
    engine = DynamicWatchlistFeatureEngine()
    sparse = engine.evaluate(feature(3))
    mature = engine.evaluate(feature(20))
    assert sparse.pullback_score > 0.0
    assert sparse.pullback_score < mature.pullback_score


def test_history_maturity_caps_at_one() -> None:
    assert DynamicWatchlistFeatureEngine._history_maturity(
        history_days=20, full_history_days=20
    ) == 1.0
    assert DynamicWatchlistFeatureEngine._history_maturity(
        history_days=40, full_history_days=20
    ) == 1.0


def test_three_day_history_has_fifteen_percent_maturity() -> None:
    assert DynamicWatchlistFeatureEngine._history_maturity(
        history_days=3, full_history_days=20
    ) == 0.15

