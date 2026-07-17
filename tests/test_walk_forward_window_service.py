"""WalkForwardWindowServiceのテスト。"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.backtest.historical_models import (
    HistoricalBar,
    HistoricalBarSeries,
    MarketTimeframe,
)
from app.backtest.walk_forward_models import (
    WalkForwardWindowPlan,
)
from app.backtest.walk_forward_window_service import (
    WalkForwardWindowService,
)


JST = ZoneInfo("Asia/Tokyo")


def create_series(
    trading_day_count: int,
) -> HistoricalBarSeries:
    """指定日数・各日2本の5分足系列を作成する。"""

    bars: list[HistoricalBar] = []
    current = datetime(
        2026,
        7,
        1,
        9,
        0,
        tzinfo=JST,
    )

    for day_index in range(trading_day_count):
        trading_date = (
            current + timedelta(days=day_index)
        )

        for minute in (0, 5):
            opened_at = trading_date.replace(
                hour=9,
                minute=minute,
            )
            base = 1000.0 + day_index

            bars.append(
                HistoricalBar(
                    code="7203",
                    timeframe=MarketTimeframe.MINUTE_5,
                    opened_at=opened_at,
                    open_price=base,
                    high_price=base + 10.0,
                    low_price=base - 10.0,
                    close_price=base + 5.0,
                    volume=1000.0,
                )
            )

    return HistoricalBarSeries(
        code="7203",
        timeframe=MarketTimeframe.MINUTE_5,
        bars=tuple(bars),
    )


def test_service_creates_rolling_windows() -> None:
    """学習3日・検証2日・2日ずつ前進する。"""

    plan = WalkForwardWindowService().create_plan(
        create_series(9),
        training_days=3,
        validation_days=2,
        step_days=2,
    )

    assert plan.window_count == 3
    assert plan.training_days == 3
    assert plan.validation_days == 2
    assert plan.step_days == 2

    first, second, third = plan.windows

    assert first.training_trading_day_count == 3
    assert first.validation_trading_day_count == 2
    assert first.training_start_date.isoformat() == "2026-07-01"
    assert first.training_end_date.isoformat() == "2026-07-03"
    assert first.validation_start_date.isoformat() == "2026-07-04"
    assert first.validation_end_date.isoformat() == "2026-07-05"

    assert second.training_start_date.isoformat() == "2026-07-03"
    assert second.validation_start_date.isoformat() == "2026-07-06"

    assert third.training_start_date.isoformat() == "2026-07-05"
    assert third.validation_end_date.isoformat() == "2026-07-09"


def test_service_defaults_step_to_validation_days() -> None:
    """step_days未指定時は検証日数分だけ前進する。"""

    plan = WalkForwardWindowService().create_plan(
        create_series(8),
        training_days=4,
        validation_days=2,
    )

    assert plan.step_days == 2
    assert plan.window_count == 2


def test_service_returns_empty_plan_when_data_is_short() -> None:
    """必要日数に満たない場合は空プランを返す。"""

    plan = WalkForwardWindowService().create_plan(
        create_series(4),
        training_days=3,
        validation_days=2,
    )

    assert plan.windows == ()
    assert plan.window_count == 0


def test_service_preserves_all_bars_in_each_period() -> None:
    """対象取引日に含まれる全ローソク足を保持する。"""

    plan = WalkForwardWindowService().create_plan(
        create_series(5),
        training_days=3,
        validation_days=2,
    )
    window = plan.windows[0]

    assert window.training_series.bar_count == 6
    assert window.validation_series.bar_count == 4
    assert all(
        bar.opened_at.date()
        <= window.training_end_date
        for bar in window.training_series.bars
    )
    assert all(
        bar.opened_at.date()
        >= window.validation_start_date
        for bar in window.validation_series.bars
    )


def test_window_id_is_stable_and_plan_get_works() -> None:
    """再現可能なIDを生成し、IDから取得できる。"""

    plan = WalkForwardWindowService().create_plan(
        create_series(5),
        training_days=3,
        validation_days=2,
    )
    window = plan.windows[0]

    assert window.window_id == (
        "wf-001_"
        "train-2026-07-01-2026-07-03_"
        "validate-2026-07-04-2026-07-05"
    )
    assert plan.get(window.window_id) == window


@pytest.mark.parametrize(
    ("training_days", "validation_days", "step_days"),
    [
        (0, 2, 2),
        (3, 0, 2),
        (3, 2, 0),
        (-1, 2, 2),
    ],
)
def test_service_rejects_non_positive_days(
    training_days: int,
    validation_days: int,
    step_days: int,
) -> None:
    """0以下の日数指定を拒否する。"""

    with pytest.raises(ValueError, match="0より大きい"):
        WalkForwardWindowService().create_plan(
            create_series(10),
            training_days=training_days,
            validation_days=validation_days,
            step_days=step_days,
        )


def test_plan_get_rejects_unknown_id() -> None:
    """存在しないウィンドウIDを拒否する。"""

    plan = WalkForwardWindowPlan(
        windows=(),
        training_days=3,
        validation_days=2,
        step_days=2,
    )

    with pytest.raises(KeyError, match="存在しません"):
        plan.get("missing")
