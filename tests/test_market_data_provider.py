"""市場データProvider共通モデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.market.market_data_provider import MarketDataTick


def test_tick_accepts_timezone_aware_datetime() -> None:
    tick = MarketDataTick(
        code="7203",
        observed_at=datetime.now(timezone.utc),
        price=2500.0,
        cumulative_volume=1000.0,
    )

    assert tick.code == "7203"
    assert tick.price == 2500.0


def test_tick_rejects_naive_datetime() -> None:
    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        MarketDataTick(
            code="7203",
            observed_at=datetime(2026, 7, 29, 9, 0),
            price=2500.0,
        )
