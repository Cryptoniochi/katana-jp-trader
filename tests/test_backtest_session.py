"""BacktestSessionのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.backtest.backtest_session import (
    BacktestSession,
    BacktestSessionStatus,
)
from app.backtest.historical_models import (
    HistoricalBar,
    HistoricalBarSeries,
    MarketTimeframe,
)
from app.backtest.market_replay import MarketReplayEngine
from app.backtest.strategy_runner import BacktestStrategyRunner
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)


STARTED_AT = datetime(
    2026,
    7,
    1,
    0,
    0,
    tzinfo=timezone.utc,
)
FINISHED_AT = STARTED_AT + timedelta(seconds=2)


class SequentialClock:
    """指定日時を順番に返す時計。"""

    def __init__(
        self,
        values: list[datetime],
    ) -> None:
        self.values = iter(values)

    def now(self) -> datetime:
        return next(self.values)


def create_series() -> HistoricalBarSeries:
    """2本の5分足系列を作成する。"""

    bars = tuple(
        HistoricalBar(
            code="7203",
            timeframe=MarketTimeframe.MINUTE_5,
            opened_at=(
                STARTED_AT
                + timedelta(minutes=index * 5)
            ),
            open_price=2500.0 + index,
            high_price=2520.0 + index,
            low_price=2490.0 + index,
            close_price=2510.0 + index,
            volume=1000.0,
        )
        for index in range(2)
    )

    return HistoricalBarSeries(
        code="7203",
        timeframe=MarketTimeframe.MINUTE_5,
        bars=bars,
    )


class SignalEveryFrameStrategy:
    """各Frameで1件のBUYシグナルを返す。"""

    strategy_name = "test-strategy"

    def evaluate(self, frame) -> tuple[TradeSignal, ...]:
        return (
            TradeSignal(
                signal_id=(
                    "signal-"
                    + frame.current_bar.opened_at.isoformat()
                ),
                code=frame.code,
                strategy_name=self.strategy_name,
                action=SignalAction.BUY,
                generated_at=frame.replayed_at,
                signal_price=frame.current_bar.close_price,
                quantity=100,
                reason="backtest session test",
            ),
        )


def create_runner() -> BacktestStrategyRunner:
    """標準的なStrategyRunnerを作成する。"""

    return BacktestStrategyRunner(
        replay_engine=MarketReplayEngine(
            create_series()
        ),
        strategy=SignalEveryFrameStrategy(),
    )


def test_session_completes_and_returns_signals() -> None:
    """セッションが完了し戦略結果を返す。"""

    session = BacktestSession(
        session_id="session-001",
        strategy_runner=create_runner(),
        now_provider=SequentialClock(
            [STARTED_AT, FINISHED_AT]
        ).now,
    )

    result = session.run()

    assert result.status is (
        BacktestSessionStatus.COMPLETED
    )
    assert result.is_completed
    assert not result.is_failed
    assert result.session_id == "session-001"
    assert result.strategy_name == "test-strategy"
    assert result.frame_count == 2
    assert result.signal_count == 2
    assert len(result.signals) == 2
    assert result.error_message is None
    assert result.duration_seconds == pytest.approx(2.0)


class FailingStrategy:
    """評価時に例外を送出する戦略。"""

    strategy_name = "failing-strategy"

    def evaluate(self, frame) -> tuple[TradeSignal, ...]:
        raise RuntimeError("strategy failed")


def create_failing_runner() -> BacktestStrategyRunner:
    """失敗するStrategyRunnerを作成する。"""

    return BacktestStrategyRunner(
        replay_engine=MarketReplayEngine(
            create_series()
        ),
        strategy=FailingStrategy(),
    )


def test_session_returns_failed_result_when_enabled() -> None:
    """継続設定時は例外を失敗結果へ変換する。"""

    session = BacktestSession(
        session_id="session-failed",
        strategy_runner=create_failing_runner(),
        now_provider=SequentialClock(
            [STARTED_AT, FINISHED_AT]
        ).now,
    )

    result = session.run(
        continue_on_error=True
    )

    assert result.status is BacktestSessionStatus.FAILED
    assert result.is_failed
    assert not result.is_completed
    assert result.strategy_result is None
    assert result.frame_count == 0
    assert result.signal_count == 0
    assert result.signals == ()
    assert result.error_message == "strategy failed"


def test_session_reraises_when_continuation_disabled() -> None:
    """継続無効時は戦略例外を再送出する。"""

    session = BacktestSession(
        session_id="session-failed",
        strategy_runner=create_failing_runner(),
        now_provider=SequentialClock(
            [STARTED_AT]
        ).now,
    )

    with pytest.raises(
        RuntimeError,
        match="strategy failed",
    ):
        session.run(
            continue_on_error=False
        )


def test_session_rejects_empty_session_id() -> None:
    """空のセッションIDを拒否する。"""

    with pytest.raises(
        ValueError,
        match="セッションID",
    ):
        BacktestSession(
            session_id=" ",
            strategy_runner=create_runner(),
        )


def test_session_rejects_naive_clock() -> None:
    """タイムゾーンなし時計を拒否する。"""

    session = BacktestSession(
        session_id="session-naive",
        strategy_runner=create_runner(),
        now_provider=lambda: datetime(
            2026,
            7,
            1,
            9,
            0,
        ),
    )

    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        session.run()
