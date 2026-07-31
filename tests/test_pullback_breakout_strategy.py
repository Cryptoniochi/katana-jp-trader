"""Pullback Breakout戦略のテスト。"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.backtest.historical_models import (
    HistoricalBar,
    HistoricalBarSeries,
    MarketTimeframe,
)
from app.backtest.market_replay import MarketReplayEngine
from app.backtest.pullback_breakout_strategy import (
    PullbackBreakoutSettings,
    PullbackBreakoutStrategy,
    PullbackExitReason,
)
from app.backtest.strategy_runner import BacktestStrategyRunner
from app.trading.signal_models import SignalAction


JST = ZoneInfo("Asia/Tokyo")


def bar(
    minute: int,
    *,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    volume: float = 1000.0,
    hour: int = 9,
) -> HistoricalBar:
    return HistoricalBar(
        code="7203",
        timeframe=MarketTimeframe.MINUTE_5,
        opened_at=datetime(
            2026,
            8,
            3,
            hour,
            minute,
            tzinfo=JST,
        ),
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        volume=volume,
    )


def entry_bars():
    return (
        bar(0, open_price=1000, high_price=1003, low_price=998, close_price=1001),
        bar(5, open_price=1001, high_price=1007, low_price=1000, close_price=1006),
        bar(10, open_price=1006, high_price=1012, low_price=1005, close_price=1010),
        bar(15, open_price=1010, high_price=1016, low_price=1009, close_price=1014),
        bar(20, open_price=1014, high_price=1015, low_price=1008, close_price=1010),
        bar(25, open_price=1010, high_price=1012, low_price=1006, close_price=1008),
        bar(30, open_price=1008, high_price=1018, low_price=1007, close_price=1017, volume=1500),
    )


def run(bars, settings=None):
    strategy = PullbackBreakoutStrategy(
        settings=settings
    )
    result = BacktestStrategyRunner(
        replay_engine=MarketReplayEngine(
            HistoricalBarSeries(
                code="7203",
                timeframe=MarketTimeframe.MINUTE_5,
                bars=bars,
            )
        ),
        strategy=strategy,
    ).run()
    return strategy, result


def test_pullback_breakout_emits_buy() -> None:
    _strategy, result = run(entry_bars())

    assert result.signal_count == 1
    signal = result.signals[0]
    assert signal.action is SignalAction.BUY
    assert signal.strategy_name == "pullback-breakout-v1"
    assert signal.metadata["pullback_rate"] > 0


def test_pullback_rejects_missing_uptrend() -> None:
    bars = tuple(
        bar(
            index * 5,
            open_price=1000,
            high_price=1002,
            low_price=998,
            close_price=1000,
            volume=1000,
        )
        for index in range(7)
    )
    strategy, result = run(bars)

    assert result.signal_count == 0
    assert (
        strategy.diagnostic_snapshot().counts[
            "uptrend_missing"
        ]
        >= 1
    )


def test_pullback_volume_filter() -> None:
    bars = list(entry_bars())
    last = bars[-1]
    bars[-1] = HistoricalBar(
        code=last.code,
        timeframe=last.timeframe,
        opened_at=last.opened_at,
        open_price=last.open_price,
        high_price=last.high_price,
        low_price=last.low_price,
        close_price=last.close_price,
        volume=500,
    )

    strategy, result = run(tuple(bars))

    assert result.signal_count == 0
    assert strategy.diagnostic_snapshot().counts[
        "volume_ratio"
    ] == 1


def test_pullback_stop_loss_exit() -> None:
    bars = entry_bars() + (
        bar(
            35,
            open_price=1014,
            high_price=1015,
            low_price=995,
            close_price=1000,
        ),
    )
    _strategy, result = run(
        bars,
        PullbackBreakoutSettings(
            trailing_stop_rate=None,
            take_profit_rate=None,
            stop_loss_rate=0.01,
        ),
    )

    assert [
        signal.action
        for signal in result.signals
    ] == [SignalAction.BUY, SignalAction.EXIT]
    assert result.signals[-1].metadata[
        "exit_reason"
    ] == PullbackExitReason.STOP_LOSS.value


def test_pullback_take_profit_exit() -> None:
    bars = entry_bars() + (
        bar(
            35,
            open_price=1014,
            high_price=1040,
            low_price=1013,
            close_price=1035,
        ),
    )
    _strategy, result = run(
        bars,
        PullbackBreakoutSettings(
            trailing_stop_rate=None,
            take_profit_rate=0.02,
        ),
    )

    assert result.signals[-1].metadata[
        "exit_reason"
    ] == PullbackExitReason.TAKE_PROFIT.value


def test_pullback_reset_clears_state() -> None:
    strategy, result = run(entry_bars())
    assert result.signal_count == 1
    strategy.reset()
    assert strategy.diagnostic_snapshot().evaluation_count == 0


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("quantity", 0),
        ("trend_window", 1),
        ("pullback_window", 0),
        ("minimum_uptrend_rate", 0),
        ("maximum_pullback_rate", 0),
    ],
)
def test_pullback_rejects_invalid_settings(
    field_name,
    value,
) -> None:
    values = {field_name: value}

    with pytest.raises(ValueError):
        PullbackBreakoutSettings(**values)
