"""Sprint 125 quality-first Trade Eligibility Gate tests."""

from dataclasses import replace
from datetime import date

from app.dynamic_watchlist.dynamic_watchlist_models import (
    DynamicWatchlistCandidate,
)
from app.dynamic_watchlist.dynamic_watchlist_service import (
    DynamicWatchlistService,
)


def _candidate(**changes) -> DynamicWatchlistCandidate:
    base = DynamicWatchlistCandidate(
        code="1234",
        latest_date=date(2026, 8, 7),
        latest_price=1000.0,
        trading_unit=100,
        purchase_amount=100000.0,
        history_days=20,
        average_volume_20d=1000000.0,
        average_turnover_20d=1000000000.0,
        volume_ratio=1.5,
        return_20d=0.03,
        breakout_ratio=0.02,
        atr_ratio=0.03,
        gap_ratio=0.01,
        vwap_distance_ratio=0.01,
        close_position_ratio=0.75,
        pullback_depth_ratio=0.02,
        breakout_score=3.0,
        momentum_score=3.0,
        liquidity_score=20.0,
        volume_score=8.0,
        volatility_score=12.0,
        gap_score=2.0,
        vwap_score=2.0,
        orb_score=5.0,
        pullback_score=3.0,
        high_breakout_score=2.0,
        technical_score=55.0,
        historical_score=0.0,
        historical_trade_count=0,
        learning_applied=False,
        learned_preferred_strategy=None,
        total_score=44.0,
        rating_tier="C",
        preferred_strategy="orb",
        selection_tier="developing",
        selected=False,
        exclusion_reasons=(),
    )
    return replace(base, **changes)


def test_quality_gate_accepts_convincing_candidate() -> None:
    assert DynamicWatchlistService._passes_trade_quality_gate(
        _candidate()
    )


def test_quality_gate_rejects_weak_strategy_setup() -> None:
    candidate = _candidate(
        preferred_strategy="pullback",
        pullback_score=3.58,
        total_score=44.36,
    )
    assert not DynamicWatchlistService._passes_trade_quality_gate(
        candidate
    )


def test_quality_gate_rejects_low_total_score() -> None:
    candidate = _candidate(
        orb_score=5.0,
        total_score=30.7,
    )
    assert not DynamicWatchlistService._passes_trade_quality_gate(
        candidate
    )


def test_quality_gate_never_overrides_existing_exclusion() -> None:
    candidate = _candidate(
        total_score=70.0,
        orb_score=9.0,
        exclusion_reasons=("insufficient_history",),
    )
    assert not DynamicWatchlistService._passes_trade_quality_gate(
        candidate
    )
