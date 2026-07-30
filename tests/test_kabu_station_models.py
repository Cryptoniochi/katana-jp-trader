"""kabuステーションAPIモデルのテスト。"""

from zoneinfo import ZoneInfo

import pytest

from app.market.kabu_station_models import (
    KabuStationSymbol,
    parse_push_tick,
)


def test_symbol_converts_to_register_payload() -> None:
    symbol = KabuStationSymbol("7203", exchange=1)

    assert symbol.to_payload() == {
        "Symbol": "7203",
        "Exchange": 1,
    }


def test_parse_push_tick() -> None:
    tick = parse_push_tick(
        {
            "Symbol": "7203",
            "Exchange": 1,
            "CurrentPrice": 2500.5,
            "CurrentPriceTime": (
                "2026-07-29T09:01:02+09:00"
            ),
            "TradingVolume": 123400,
        }
    )

    assert tick is not None
    assert tick.code == "7203"
    assert tick.price == 2500.5
    assert tick.cumulative_volume == 123400
    assert tick.observed_at.tzinfo == ZoneInfo(
        "Asia/Tokyo"
    )


def test_parse_push_tick_returns_none_without_price() -> None:
    assert parse_push_tick(
        {
            "Symbol": "7203",
            "CurrentPriceTime": (
                "2026-07-29T09:01:02+09:00"
            ),
        }
    ) is None


def test_symbol_rejects_non_numeric_code() -> None:
    with pytest.raises(ValueError, match="数字"):
        KabuStationSymbol("ABCD")
