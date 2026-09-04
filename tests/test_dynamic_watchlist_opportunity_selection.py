"""Dynamic Watchlist 2.0 opportunity-first selection tests."""

from datetime import date

from app.dynamic_watchlist.dynamic_watchlist_models import DynamicWatchlistCandidate
from app.dynamic_watchlist.dynamic_watchlist_service import DynamicWatchlistService


def _candidate(
    code: str,
    *,
    total_score: float = 60.0,
    atr_ratio: float = 0.03,
    volume_ratio: float = 1.5,
    orb_score: float = 7.0,
    turnover: float = 1_000_000_000.0,
) -> DynamicWatchlistCandidate:
    return DynamicWatchlistCandidate(
        code=code,
        latest_date=date(2026, 9, 3),
        latest_price=1000.0,
        trading_unit=100,
        purchase_amount=100000.0,
        history_days=20,
        average_volume_20d=1_000_000.0,
        average_turnover_20d=turnover,
        volume_ratio=volume_ratio,
        return_20d=0.05,
        breakout_ratio=0.01,
        atr_ratio=atr_ratio,
        gap_ratio=0.01,
        vwap_distance_ratio=0.005,
        close_position_ratio=0.8,
        pullback_depth_ratio=0.03,
        breakout_score=10.0,
        momentum_score=10.0,
        liquidity_score=10.0,
        volume_score=10.0,
        volatility_score=10.0,
        gap_score=5.0,
        vwap_score=3.0,
        orb_score=orb_score,
        pullback_score=5.0,
        high_breakout_score=5.0,
        technical_score=total_score,
        historical_score=0.0,
        historical_trade_count=0,
        learning_applied=False,
        learned_preferred_strategy=None,
        total_score=total_score,
        rating_tier="B",
        preferred_strategy="orb",
        selection_tier="strict",
        selected=False,
        exclusion_reasons=(),
    )


def test_quality_gate_rejects_dormant_low_atr_candidate() -> None:
    candidate = _candidate("1111", atr_ratio=0.008)
    assert not DynamicWatchlistService._passes_trade_quality_gate(candidate)


def test_quality_gate_rejects_weak_current_participation() -> None:
    candidate = _candidate("2222", volume_ratio=0.70)
    assert not DynamicWatchlistService._passes_trade_quality_gate(candidate)


def test_quality_gate_requires_concrete_strategy_setup() -> None:
    candidate = _candidate("3333", orb_score=4.5)
    assert not DynamicWatchlistService._passes_trade_quality_gate(candidate)


def test_quality_gate_accepts_active_tradeable_candidate() -> None:
    candidate = _candidate("4444")
    assert DynamicWatchlistService._passes_trade_quality_gate(candidate)


def test_ranking_uses_current_opportunity_before_static_turnover() -> None:
    active = _candidate(
        "5555",
        volume_ratio=2.0,
        orb_score=8.0,
        turnover=500_000_000.0,
    )
    mega_cap = _candidate(
        "6666",
        volume_ratio=1.0,
        orb_score=6.0,
        turnover=5_000_000_000.0,
    )
    ranked = sorted(
        (mega_cap, active),
        key=DynamicWatchlistService._ranking_key,
    )
    assert ranked[0].code == "5555"
