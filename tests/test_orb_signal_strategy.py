"""イベント駆動型ORB戦略のテスト。"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.backtest.historical_models import (
    HistoricalBar,
    HistoricalBarSeries,
    MarketTimeframe,
)
from app.backtest.market_replay import MarketReplayEngine
from app.backtest.orb_signal_strategy import (
    OrbExitReason,
    OrbSignalStrategy,
    OrbSignalStrategySettings,
)
from app.backtest.strategy_runner import BacktestStrategyRunner
from app.trading.signal_models import SignalAction


JST = ZoneInfo("Asia/Tokyo")


def bar(
    hour: int,
    minute: int,
    *,
    open_price: float = 1000.0,
    high_price: float = 1010.0,
    low_price: float = 990.0,
    close_price: float = 1000.0,
    volume: float = 1000.0,
    timeframe: MarketTimeframe = MarketTimeframe.MINUTE_5,
) -> HistoricalBar:
    """指定時刻のテスト用ローソク足を作成する。"""

    return HistoricalBar(
        code="7203",
        timeframe=timeframe,
        opened_at=datetime(
            2026,
            7,
            1,
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


def run_strategy(
    bars: tuple[HistoricalBar, ...],
    *,
    settings: OrbSignalStrategySettings | None = None,
):
    """指定履歴でORB戦略を実行する。"""

    series = HistoricalBarSeries(
        code="7203",
        timeframe=bars[0].timeframe,
        bars=bars,
    )
    strategy = OrbSignalStrategy(
        settings=settings
    )
    result = BacktestStrategyRunner(
        replay_engine=MarketReplayEngine(series),
        strategy=strategy,
    ).run()

    return strategy, result


def test_orb_emits_buy_after_opening_range_breakout() -> None:
    """オープニングレンジ高値突破でBUYを生成する。"""

    _strategy, result = run_strategy(
        (
            bar(9, 0, high_price=1005.0),
            bar(9, 5, high_price=1010.0),
            bar(9, 10, high_price=1008.0),
            bar(9, 15, high_price=1009.0),
            bar(
                9,
                20,
                high_price=1015.0,
                low_price=1000.0,
                close_price=1012.0,
                volume=2000.0,
            ),
        )
    )

    assert result.signal_count == 1

    signal = result.signals[0]

    assert signal.action is SignalAction.BUY
    assert signal.signal_price == pytest.approx(1012.0)
    assert signal.metadata["opening_range_high"] == pytest.approx(
        1010.0
    )


def test_orb_does_not_use_future_bars() -> None:
    """ブレイク前のFrameではシグナルを生成しない。"""

    strategy = OrbSignalStrategy()
    frames = MarketReplayEngine(
        HistoricalBarSeries(
            code="7203",
            timeframe=MarketTimeframe.MINUTE_5,
            bars=(
                bar(9, 0, high_price=1005.0),
                bar(9, 5, high_price=1010.0),
                bar(9, 10, high_price=1008.0),
                bar(9, 15, high_price=1009.0),
                bar(9, 20, high_price=1015.0),
            ),
        )
    ).replay()

    assert all(
        strategy.evaluate(frame) == ()
        for frame in frames[:-1]
    )
    assert strategy.evaluate(frames[-1])[0].action is (
        SignalAction.BUY
    )


def test_orb_prioritizes_stop_loss_when_both_hit() -> None:
    """同一足で損切りと利確に到達した場合は損切りを優先する。"""

    _strategy, result = run_strategy(
        (
            bar(9, 0, high_price=1000.0),
            bar(9, 5, high_price=1000.0),
            bar(9, 10, high_price=1000.0),
            bar(9, 15, high_price=1000.0),
            bar(
                9,
                20,
                high_price=1010.0,
                close_price=1005.0,
            ),
            bar(
                9,
                25,
                high_price=1030.0,
                low_price=970.0,
                close_price=1000.0,
            ),
        ),
        settings=OrbSignalStrategySettings(
            stop_loss_rate=0.02,
            take_profit_rate=0.02,
        ),
    )

    assert result.signal_count == 2

    exit_signal = result.signals[1]

    assert exit_signal.action is SignalAction.EXIT
    assert exit_signal.metadata["exit_reason"] == (
        OrbExitReason.STOP_LOSS.value
    )
    assert exit_signal.signal_price == pytest.approx(
        1005.0 * 0.98
    )


def test_orb_emits_take_profit_exit() -> None:
    """利確価格到達でEXITを生成する。"""

    _strategy, result = run_strategy(
        (
            bar(9, 0, high_price=1000.0),
            bar(9, 5, high_price=1000.0),
            bar(9, 10, high_price=1000.0),
            bar(9, 15, high_price=1000.0),
            bar(
                9,
                20,
                high_price=1010.0,
                close_price=1005.0,
            ),
            bar(
                9,
                25,
                high_price=1020.0,
                low_price=1000.0,
                close_price=1015.0,
            ),
        ),
        settings=OrbSignalStrategySettings(
            take_profit_rate=0.01,
        ),
    )

    assert result.signals[1].metadata["exit_reason"] == (
        OrbExitReason.TAKE_PROFIT.value
    )


def test_orb_emits_force_exit() -> None:
    """強制決済時刻にEXITを生成する。"""

    _strategy, result = run_strategy(
        (
            bar(9, 0, high_price=1000.0),
            bar(9, 5, high_price=1000.0),
            bar(9, 10, high_price=1000.0),
            bar(9, 15, high_price=1000.0),
            bar(
                9,
                20,
                high_price=1010.0,
                close_price=1005.0,
            ),
            bar(
                15,
                30,
                high_price=1010.0,
                low_price=995.0,
                close_price=1002.0,
            ),
        )
    )

    assert result.signal_count == 2
    assert result.signals[1].metadata["exit_reason"] == (
        OrbExitReason.FORCE_EXIT.value
    )


def test_orb_enters_at_most_once_per_day() -> None:
    """決済後も同じ営業日には再エントリーしない。"""

    _strategy, result = run_strategy(
        (
            bar(9, 0, high_price=1000.0),
            bar(9, 5, high_price=1000.0),
            bar(9, 10, high_price=1000.0),
            bar(9, 15, high_price=1000.0),
            bar(
                9,
                20,
                high_price=1010.0,
                close_price=1005.0,
            ),
            bar(
                9,
                25,
                high_price=1020.0,
                close_price=1015.0,
            ),
            bar(
                9,
                30,
                high_price=1030.0,
                close_price=1025.0,
            ),
        ),
        settings=OrbSignalStrategySettings(
            take_profit_rate=0.01,
        ),
    )

    assert [
        signal.action
        for signal in result.signals
    ] == [
        SignalAction.BUY,
        SignalAction.EXIT,
    ]


def test_orb_applies_volume_filter() -> None:
    """出来高倍率不足ならブレイクを見送る。"""

    _strategy, result = run_strategy(
        (
            bar(9, 0, high_price=1000.0, volume=1000.0),
            bar(9, 5, high_price=1000.0, volume=1000.0),
            bar(9, 10, high_price=1000.0, volume=1000.0),
            bar(9, 15, high_price=1000.0, volume=1000.0),
            bar(
                9,
                20,
                high_price=1010.0,
                close_price=1005.0,
                volume=1500.0,
            ),
        ),
        settings=OrbSignalStrategySettings(
            breakout_volume_ratio=2.0,
        ),
    )

    assert result.signal_count == 0


def test_orb_rejects_non_five_minute_frame() -> None:
    """5分足以外を拒否する。"""

    strategy = OrbSignalStrategy()
    frame = MarketReplayEngine(
        HistoricalBarSeries(
            code="7203",
            timeframe=MarketTimeframe.MINUTE_1,
            bars=(
                bar(
                    9,
                    0,
                    timeframe=MarketTimeframe.MINUTE_1,
                ),
            ),
        )
    ).replay()[0]

    with pytest.raises(ValueError, match="5分足"):
        strategy.evaluate(frame)


def test_orb_reset_clears_state() -> None:
    """reset後は同じ履歴を再実行できる。"""

    bars = (
        bar(9, 0, high_price=1000.0),
        bar(9, 5, high_price=1000.0),
        bar(9, 10, high_price=1000.0),
        bar(9, 15, high_price=1000.0),
        bar(
            9,
            20,
            high_price=1010.0,
            close_price=1005.0,
        ),
    )
    series = HistoricalBarSeries(
        code="7203",
        timeframe=MarketTimeframe.MINUTE_5,
        bars=bars,
    )
    frames = MarketReplayEngine(series).replay()
    strategy = OrbSignalStrategy()

    first = tuple(
        signal
        for frame in frames
        for signal in strategy.evaluate(frame)
    )

    strategy.reset()

    second = tuple(
        signal
        for frame in frames
        for signal in strategy.evaluate(frame)
    )

    assert first == second
