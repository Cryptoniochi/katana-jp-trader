"""Sprint 130-1 history maturity guard tests."""

from app.universe.universe_primary_screener import UniversePrimaryScreener


def metric(history_count: int, return_5d: float = 0.10) -> dict[str, object]:
    return {
        "atr_ratio": 0.04,
        "volume_ratio": 2.0,
        "return_5d": return_5d,
        "breakout_ratio": 0.04,
        "range_expansion_ratio": 2.0,
        "gap_ratio": 0.03,
        "close_position_ratio": 1.0,
        "average_turnover": 1_000_000_000.0,
        "history_count": history_count,
    }


def test_sparse_history_is_discounted() -> None:
    sparse, _ = UniversePrimaryScreener._score(metric(3), 200_000.0)
    mature, _ = UniversePrimaryScreener._score(metric(20), 200_000.0)
    assert sparse < mature


def test_momentum_is_disabled_before_five_observations() -> None:
    baseline, _ = UniversePrimaryScreener._score(metric(4, 0.0), 200_000.0)
    fake, _ = UniversePrimaryScreener._score(metric(4, 0.50), 200_000.0)
    assert fake == baseline


def test_momentum_is_enabled_at_five_observations() -> None:
    baseline, _ = UniversePrimaryScreener._score(metric(5, 0.0), 200_000.0)
    active, _ = UniversePrimaryScreener._score(metric(5, 0.10), 200_000.0)
    assert active > baseline


def test_history_discount_caps_at_twenty_observations() -> None:
    twenty, _ = UniversePrimaryScreener._score(metric(20), 200_000.0)
    forty, _ = UniversePrimaryScreener._score(metric(40), 200_000.0)
    assert twenty == forty
