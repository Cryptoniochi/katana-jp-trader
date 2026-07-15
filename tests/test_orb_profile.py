"""ORB共通プロファイルのテスト。"""

from datetime import time

import pytest

from app.strategy.orb_profile import (
    DEFAULT_ORB_PROFILE,
    OrbStrategyProfile,
)


def test_default_profile_uses_relaxed_liquidity_filters() -> None:
    """既定プロファイルに段階的緩和条件を設定する。"""

    strategy = DEFAULT_ORB_PROFILE.create_strategy()

    assert strategy.min_opening_range_volume == 200_000
    assert strategy.min_opening_range_turnover == pytest.approx(200_000_000.0)

    assert strategy.min_breakout_volume == 50_000
    assert strategy.breakout_volume_ratio == pytest.approx(0.8)
    assert strategy.min_breakout_turnover == pytest.approx(50_000_000.0)

    assert strategy.min_price == pytest.approx(500.0)
    assert strategy.max_price == pytest.approx(20_000.0)


def test_profile_creates_strategy() -> None:
    """プロファイルからORB戦略を作成できる。"""

    profile = OrbStrategyProfile(
        quantity=200,
        opening_range_end=time(9, 10),
        stop_loss_rate=0.008,
        take_profit_rate=0.015,
    )

    strategy = profile.create_strategy()

    assert strategy.quantity == 200
    assert strategy.opening_range_end == time(9, 10)
    assert strategy.stop_loss_rate == pytest.approx(0.008)
    assert strategy.take_profit_rate == pytest.approx(0.015)


def test_profile_accepts_parameter_overrides() -> None:
    """最適化用に一部パラメータを上書きできる。"""

    profile = OrbStrategyProfile()

    strategy = profile.create_strategy(
        opening_range_end=time(9, 5),
        stop_loss_rate=0.005,
        take_profit_rate=0.03,
    )

    assert strategy.opening_range_end == time(9, 5)
    assert strategy.stop_loss_rate == pytest.approx(0.005)
    assert strategy.take_profit_rate == pytest.approx(0.03)

    assert strategy.min_breakout_volume == 50_000
    assert strategy.breakout_volume_ratio == pytest.approx(0.8)
