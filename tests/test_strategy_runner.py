"""BacktestStrategyRunnerのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.backtest.historical_models import (
    HistoricalBar,
    HistoricalBarSeries,
    MarketTimeframe,
)
from app.backtest.market_replay import MarketReplayEngine
from app.backtest.strategy_runner import (
    BacktestStrategyRunner,
    BacktestStrategyValidationError,
)
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)


BASE_TIME = datetime(
    2026,
    7,
    1,
    0,
    0,
    tzinfo=timezone.utc,
)


def create_series(
    *,
    count: int = 4,
) -> HistoricalBarSeries:
    """テスト用5分足系列を作成する。"""

    bars = tuple(
        HistoricalBar(
            code="7203",
            timeframe=MarketTimeframe.MINUTE_5,
            opened_at=(
                BASE_TIME
                + timedelta(minutes=index * 5)
            ),
            open_price=2500.0 + index,
            high_price=2520.0 + index,
            low_price=2490.0 + index,
            close_price=2510.0 + index,
            volume=1000.0,
        )
        for index in range(count)
    )

    return HistoricalBarSeries(
        code="7203",
        timeframe=MarketTimeframe.MINUTE_5,
        bars=bars,
    )


def create_signal(
    *,
    frame,
    signal_id: str,
    strategy_name: str = "test-strategy",
    code: str = "7203",
    generated_at: datetime | None = None,
) -> TradeSignal:
    """現在Frameに対応するテスト用シグナルを作成する。"""

    return TradeSignal(
        signal_id=signal_id,
        code=code,
        strategy_name=strategy_name,
        action=SignalAction.BUY,
        generated_at=(
            generated_at
            if generated_at is not None
            else frame.replayed_at
        ),
        signal_price=frame.current_bar.close_price,
        quantity=100,
        reason="backtest test signal",
    )


class CloseAboveStrategy:
    """指定終値を超えたFrameでBUYを生成する戦略。"""

    strategy_name = "test-strategy"

    def __init__(self, threshold: float) -> None:
        self.threshold = threshold
        self.visible_counts: list[int] = []

    def evaluate(self, frame) -> tuple[TradeSignal, ...]:
        self.visible_counts.append(
            len(frame.visible_bars)
        )

        if frame.current_bar.close_price <= self.threshold:
            return ()

        return (
            create_signal(
                frame=frame,
                signal_id=(
                    "signal-"
                    + frame.current_bar.opened_at.isoformat()
                ),
            ),
        )


def test_runner_executes_strategy_for_each_frame() -> None:
    """全Frameを時系列順に戦略へ渡す。"""

    strategy = CloseAboveStrategy(
        threshold=2511.0
    )
    runner = BacktestStrategyRunner(
        replay_engine=MarketReplayEngine(
            create_series(count=4)
        ),
        strategy=strategy,
    )

    result = runner.run()

    assert result.strategy_name == "test-strategy"
    assert result.frame_count == 4
    assert result.signal_count == 2
    assert result.signaled_frame_count == 2
    assert strategy.visible_counts == [1, 2, 3, 4]

    assert [
        signal.signal_price
        for signal in result.signals
    ] == [
        2512.0,
        2513.0,
    ]


def test_runner_returns_empty_result_without_frames() -> None:
    """履歴が空なら空の実行結果を返す。"""

    strategy = CloseAboveStrategy(
        threshold=0.0
    )
    runner = BacktestStrategyRunner(
        replay_engine=MarketReplayEngine(
            create_series(count=0)
        ),
        strategy=strategy,
    )

    result = runner.run()

    assert result.frame_results == ()
    assert result.signals == ()
    assert result.frame_count == 0
    assert result.signal_count == 0
    assert result.signaled_frame_count == 0


class WrongCodeStrategy:
    """異なる銘柄コードのシグナルを生成する。"""

    strategy_name = "test-strategy"

    def evaluate(self, frame) -> tuple[TradeSignal, ...]:
        return (
            create_signal(
                frame=frame,
                signal_id="wrong-code",
                code="8306",
            ),
        )


def test_runner_rejects_wrong_signal_code() -> None:
    """現在Frameと異なる銘柄のシグナルを拒否する。"""

    runner = BacktestStrategyRunner(
        replay_engine=MarketReplayEngine(
            create_series(count=1)
        ),
        strategy=WrongCodeStrategy(),
    )

    with pytest.raises(
        BacktestStrategyValidationError,
        match="銘柄コード",
    ):
        runner.run()


class WrongNameStrategy:
    """異なる戦略名のシグナルを生成する。"""

    strategy_name = "test-strategy"

    def evaluate(self, frame) -> tuple[TradeSignal, ...]:
        return (
            create_signal(
                frame=frame,
                signal_id="wrong-name",
                strategy_name="another-strategy",
            ),
        )


def test_runner_rejects_wrong_strategy_name() -> None:
    """Runnerと異なる戦略名のシグナルを拒否する。"""

    runner = BacktestStrategyRunner(
        replay_engine=MarketReplayEngine(
            create_series(count=1)
        ),
        strategy=WrongNameStrategy(),
    )

    with pytest.raises(
        BacktestStrategyValidationError,
        match="戦略名",
    ):
        runner.run()


class FutureSignalStrategy:
    """未来日時のシグナルを生成する。"""

    strategy_name = "test-strategy"

    def evaluate(self, frame) -> tuple[TradeSignal, ...]:
        return (
            create_signal(
                frame=frame,
                signal_id="future-signal",
                generated_at=(
                    frame.replayed_at
                    + timedelta(seconds=1)
                ),
            ),
        )


def test_runner_rejects_future_signal() -> None:
    """現在のリプレイ時刻より未来のシグナルを拒否する。"""

    runner = BacktestStrategyRunner(
        replay_engine=MarketReplayEngine(
            create_series(count=1)
        ),
        strategy=FutureSignalStrategy(),
    )

    with pytest.raises(
        BacktestStrategyValidationError,
        match="未来",
    ):
        runner.run()


class DuplicateSignalStrategy:
    """同じシグナルIDを毎回生成する。"""

    strategy_name = "test-strategy"

    def evaluate(self, frame) -> tuple[TradeSignal, ...]:
        return (
            create_signal(
                frame=frame,
                signal_id="duplicate-signal",
            ),
        )


def test_runner_rejects_duplicate_signal_id() -> None:
    """複数Frameで重複したシグナルIDを拒否する。"""

    runner = BacktestStrategyRunner(
        replay_engine=MarketReplayEngine(
            create_series(count=2)
        ),
        strategy=DuplicateSignalStrategy(),
    )

    with pytest.raises(
        BacktestStrategyValidationError,
        match="シグナルID",
    ):
        runner.run()


class EmptyNameStrategy:
    """空の戦略名を返す。"""

    strategy_name = " "

    def evaluate(self, frame) -> tuple[TradeSignal, ...]:
        return ()


def test_runner_rejects_empty_strategy_name() -> None:
    """空の戦略名を拒否する。"""

    with pytest.raises(ValueError, match="戦略名"):
        BacktestStrategyRunner(
            replay_engine=MarketReplayEngine(
                create_series(count=1)
            ),
            strategy=EmptyNameStrategy(),
        )
