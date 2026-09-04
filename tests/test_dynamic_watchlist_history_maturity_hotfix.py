"""Sprint 133-1: sparse history must be discounted, not made untradeable."""

from app.dynamic_watchlist.dynamic_watchlist_feature_engine import (
    DynamicWatchlistFeatureEngine,
    DynamicWatchlistFeatureInput,
)


def _feature(history_days: int) -> DynamicWatchlistFeatureInput:
    return DynamicWatchlistFeatureInput(
        average_turnover_20d=1_000_000_000.0,
        volume_ratio=3.0,
        atr_ratio=0.04,
        gap_ratio=0.02,
        vwap_distance_ratio=0.005,
        return_20d=0.12,
        breakout_ratio=0.04,
        close_position_ratio=0.90,
        pullback_depth_ratio=0.035,
        history_days=history_days,
        full_history_days=20,
    )


def test_sparse_history_is_discounted_but_not_zeroed() -> None:
    engine = DynamicWatchlistFeatureEngine()
    sparse = engine.evaluate(_feature(3))
    mature = engine.evaluate(_feature(20))
    assert sparse.total_score > 0.0
    assert sparse.total_score < mature.total_score


def test_three_day_orb_preserves_day_local_signal() -> None:
    score = DynamicWatchlistFeatureEngine().evaluate(_feature(3))
    assert score.orb_score >= 2.5


def test_sparse_breakout_is_below_mature_breakout() -> None:
    engine = DynamicWatchlistFeatureEngine()
    sparse = engine.evaluate(_feature(3))
    mature = engine.evaluate(_feature(20))
    assert sparse.high_breakout_score < mature.high_breakout_score


def test_maturity_caps_at_one() -> None:
    assert DynamicWatchlistFeatureEngine._history_maturity(
        history_days=40,
        full_history_days=20,
    ) == 1.0
