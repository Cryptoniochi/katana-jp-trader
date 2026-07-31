"""HighBreakoutScreenerのテスト。"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.backtest.historical_models import (
    HistoricalBar,
    HistoricalBarSeries,
    MarketTimeframe,
)
from app.strategy.high_breakout_models import (
    HighBreakoutScreenerSettings,
    HighBreakoutType,
)
from app.strategy.high_breakout_screener import (
    HighBreakoutScreener,
)


JST = ZoneInfo("Asia/Tokyo")


def build_series(
    *,
    code: str = "7203",
    days: int = 65,
    breakout: bool = True,
    volume_ratio: float = 2.0,
    last_close: float | None = None,
) -> HistoricalBarSeries:
    start = datetime(
        2026,
        1,
        5,
        0,
        0,
        tzinfo=JST,
    )
    bars = []

    for index in range(days - 1):
        close = 1000.0 + index
        bars.append(
            HistoricalBar(
                code=code,
                timeframe=MarketTimeframe.DAY_1,
                opened_at=(
                    start + timedelta(days=index)
                ),
                open_price=close - 5,
                high_price=close + 5,
                low_price=close - 10,
                close_price=close,
                volume=100_000,
            )
        )

    previous_high = max(
        bar.high_price
        for bar in bars
    )
    close = (
        last_close
        if last_close is not None
        else (
            previous_high + 10
            if breakout
            else previous_high - 1
        )
    )
    bars.append(
        HistoricalBar(
            code=code,
            timeframe=MarketTimeframe.DAY_1,
            opened_at=(
                start + timedelta(days=days - 1)
            ),
            open_price=close - 5,
            high_price=close + 5,
            low_price=close - 15,
            close_price=close,
            volume=int(
                100_000 * volume_ratio
            ),
        )
    )

    return HistoricalBarSeries(
        code=code,
        timeframe=MarketTimeframe.DAY_1,
        bars=tuple(bars),
    )


def permissive_settings():
    return HighBreakoutScreenerSettings(
        minimum_turnover=0,
        minimum_atr_rate=None,
        maximum_atr_rate=None,
    )


def test_screener_detects_20_60_and_ytd_breakout() -> None:
    candidate = HighBreakoutScreener(
        settings=permissive_settings()
    ).screen(build_series())

    assert candidate is not None
    assert set(candidate.breakout_types) == {
        HighBreakoutType.DAY_20,
        HighBreakoutType.DAY_60,
        HighBreakoutType.YEAR_TO_DATE,
    }
    assert candidate.volume_ratio == pytest.approx(2.0)
    assert candidate.score > 0


def test_screener_returns_none_without_breakout() -> None:
    candidate = HighBreakoutScreener(
        settings=permissive_settings()
    ).screen(
        build_series(breakout=False)
    )

    assert candidate is None


def test_screener_applies_volume_ratio() -> None:
    candidate = HighBreakoutScreener(
        settings=HighBreakoutScreenerSettings(
            minimum_volume_ratio=2.5,
            minimum_turnover=0,
            minimum_atr_rate=None,
            maximum_atr_rate=None,
        )
    ).screen(
        build_series(volume_ratio=2.0)
    )

    assert candidate is None


def test_screener_applies_price_filter() -> None:
    candidate = HighBreakoutScreener(
        settings=HighBreakoutScreenerSettings(
            minimum_price=2000.0,
            minimum_turnover=0,
            minimum_atr_rate=None,
            maximum_atr_rate=None,
        )
    ).screen(build_series())

    assert candidate is None


def test_screener_rejects_insufficient_history() -> None:
    candidate = HighBreakoutScreener(
        settings=permissive_settings()
    ).screen(
        build_series(days=10)
    )

    assert candidate is None


def test_screener_requires_daily_timeframe() -> None:
    series = build_series()
    invalid = HistoricalBarSeries(
        code=series.code,
        timeframe=MarketTimeframe.MINUTE_5,
        bars=tuple(
            HistoricalBar(
                code=bar.code,
                timeframe=MarketTimeframe.MINUTE_5,
                opened_at=bar.opened_at,
                open_price=bar.open_price,
                high_price=bar.high_price,
                low_price=bar.low_price,
                close_price=bar.close_price,
                volume=bar.volume,
            )
            for bar in series.bars
        ),
    )

    with pytest.raises(ValueError, match="日足"):
        HighBreakoutScreener().screen(invalid)


def test_screen_many_orders_by_score() -> None:
    screener = HighBreakoutScreener(
        settings=permissive_settings()
    )

    results = screener.screen_many(
        (
            build_series(
                code="7203",
                volume_ratio=2.0,
            ),
            build_series(
                code="6758",
                volume_ratio=3.0,
            ),
        )
    )

    assert [
        item.code
        for item in results
    ] == ["6758", "7203"]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("minimum_history_days", 0),
        ("short_lookback_days", 0),
        ("long_lookback_days", 0),
        ("volume_lookback_days", 0),
        ("atr_lookback_days", 0),
        ("minimum_volume_ratio", 0),
        ("minimum_turnover", -1),
    ],
)
def test_settings_rejects_invalid_values(
    field_name,
    value,
) -> None:
    with pytest.raises(ValueError):
        HighBreakoutScreenerSettings(
            **{field_name: value}
        )
