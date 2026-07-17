"""LiveTradingOrchestratorのテスト。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.live.live_orchestrator import (
    LiveTradingOrchestrator,
)
from app.live.live_orchestrator_models import (
    LiveRunStopReason,
)
from app.market.realtime_models import (
    MarketSessionSnapshot,
    MarketSessionState,
    RealtimeMarketPollResult,
    RealtimePollDecision,
)
from app.market.realtime_paper_trading_service import (
    RealtimePaperTradingResult,
    RealtimePaperTradingStatus,
)
from app.market.realtime_signal_models import (
    RealtimeSignalDecision,
    RealtimeSignalProcessResult,
)
from app.backtest.queue_execution_service import (
    BacktestQueueExecutionBatchResult,
)
from app.backtest.backtest_portfolio_update_service import (
    BacktestPortfolioBatchUpdateResult,
)


def session(
    observed_at: datetime,
) -> MarketSessionSnapshot:
    """取引時間中の市場状態を作成する。"""

    return MarketSessionSnapshot(
        observed_at=observed_at,
        trading_date=observed_at.date(),
        is_trading_day=True,
        state=MarketSessionState.MORNING,
    )


def market_result(
    observed_at: datetime,
    *,
    decision: RealtimePollDecision,
) -> RealtimeMarketPollResult:
    """市場監視結果を作成する。"""

    return RealtimeMarketPollResult(
        session=session(observed_at),
        decision=decision,
        code_count=1,
        fetched_bar_count=0,
        new_bar_count=0,
        saved_bar_count=0,
        new_bars=(),
    )


def paper_result() -> RealtimePaperTradingResult:
    """空の正常Paper Trading結果を作成する。"""

    return RealtimePaperTradingResult(
        status=RealtimePaperTradingStatus.COMPLETED,
        signal_result=RealtimeSignalProcessResult(
            decision=RealtimeSignalDecision.NO_NEW_BAR,
            input_bar_count=0,
            processed_bar_count=0,
            skipped_duplicate_count=0,
            signal_count=0,
            signals=(),
        ),
        queue_results=(),
        execution_result=BacktestQueueExecutionBatchResult(
            items=()
        ),
        portfolio_result=BacktestPortfolioBatchUpdateResult(
            items=()
        ),
        error_message=None,
    )


class FakeClock:
    """呼出ごとに時刻を進める時計。"""

    def __init__(self) -> None:
        self.current = datetime(
            2026,
            7,
            17,
            0,
            0,
            tzinfo=timezone.utc,
        )

    def now(self) -> datetime:
        value = self.current
        self.current += timedelta(seconds=1)
        return value


class FakeMonitor:
    """市場監視呼出を記録する。"""

    def __init__(
        self,
        decision: RealtimePollDecision,
    ) -> None:
        self.decision = decision
        self.calls = 0
        self.raise_error = False

    def poll(
        self,
        *,
        codes,
        observed_at: datetime,
    ) -> RealtimeMarketPollResult:
        self.calls += 1

        if self.raise_error:
            raise RuntimeError("monitor failed")

        return market_result(
            observed_at,
            decision=self.decision,
        )


class FakePaperService:
    """Paper Trading呼出を記録する。"""

    def __init__(self) -> None:
        self.calls = 0
        self.raise_error = False

    def process(
        self,
        prices,
        *,
        continue_on_error: bool = False,
    ) -> RealtimePaperTradingResult:
        self.calls += 1

        if self.raise_error:
            raise RuntimeError("paper failed")

        return paper_result()


def test_run_stops_at_max_cycles() -> None:
    """最大サイクル数で終了する。"""

    clock = FakeClock()
    monitor = FakeMonitor(
        RealtimePollDecision.NO_NEW_BAR
    )
    paper = FakePaperService()
    sleeps: list[float] = []

    result = LiveTradingOrchestrator(
        market_monitor=monitor,
        paper_trading_service=paper,
        now_provider=clock.now,
        sleeper=sleeps.append,
    ).run(
        codes=("7203",),
        poll_interval_seconds=5.0,
        max_cycles=3,
    )

    assert result.stop_reason is (
        LiveRunStopReason.MAX_CYCLES_REACHED
    )
    assert result.cycle_count == 3
    assert result.completed_cycle_count == 3
    assert monitor.calls == 3
    assert paper.calls == 0
    assert sleeps == [5.0, 5.0]


def test_run_stops_when_requested() -> None:
    """停止要求成立時に安全に終了する。"""

    clock = FakeClock()
    monitor = FakeMonitor(
        RealtimePollDecision.NO_NEW_BAR
    )
    paper = FakePaperService()
    checks = 0

    def stop_requested() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 3

    result = LiveTradingOrchestrator(
        market_monitor=monitor,
        paper_trading_service=paper,
        now_provider=clock.now,
        sleeper=lambda _seconds: None,
        stop_requested=stop_requested,
    ).run(
        codes=("7203",),
    )

    assert result.stop_reason is (
        LiveRunStopReason.STOP_REQUESTED
    )
    assert result.cycle_count == 1
    assert monitor.calls == 1


def test_cycle_calls_paper_only_for_new_bars() -> None:
    """新規保存足がある場合だけPaper Tradingを呼ぶ。"""

    clock = FakeClock()
    monitor = FakeMonitor(
        RealtimePollDecision.NO_NEW_BAR
    )
    paper = FakePaperService()
    orchestrator = LiveTradingOrchestrator(
        market_monitor=monitor,
        paper_trading_service=paper,
        now_provider=clock.now,
        sleeper=lambda _seconds: None,
    )

    first = orchestrator.run_cycle(
        cycle_number=1,
        codes=("7203",),
    )

    assert first.is_completed
    assert paper.calls == 0

    monitor.decision = (
        RealtimePollDecision.NEW_BARS_SAVED
    )
    invalid_new_bar_result = market_result(
        datetime.now(timezone.utc),
        decision=RealtimePollDecision.NO_NEW_BAR,
    )
    monitor.poll = lambda **_kwargs: invalid_new_bar_result

    second = orchestrator.run_cycle(
        cycle_number=2,
        codes=("7203",),
    )

    assert second.is_completed
    assert paper.calls == 0


def test_cycle_converts_error_to_failed_result() -> None:
    """継続モードでは例外を失敗サイクルへ変換する。"""

    clock = FakeClock()
    monitor = FakeMonitor(
        RealtimePollDecision.NO_NEW_BAR
    )
    monitor.raise_error = True

    result = LiveTradingOrchestrator(
        market_monitor=monitor,
        paper_trading_service=FakePaperService(),
        now_provider=clock.now,
    ).run_cycle(
        cycle_number=1,
        codes=("7203",),
        continue_on_error=True,
    )

    assert result.is_failed
    assert result.error_message == "monitor failed"


def test_cycle_raises_error_when_not_continuing() -> None:
    """停止モードでは例外をそのまま送出する。"""

    clock = FakeClock()
    monitor = FakeMonitor(
        RealtimePollDecision.NO_NEW_BAR
    )
    monitor.raise_error = True

    with pytest.raises(RuntimeError, match="monitor failed"):
        LiveTradingOrchestrator(
            market_monitor=monitor,
            paper_trading_service=FakePaperService(),
            now_provider=clock.now,
        ).run_cycle(
            cycle_number=1,
            codes=("7203",),
            continue_on_error=False,
        )


def test_run_continues_after_failed_cycle() -> None:
    """継続モードでは失敗後も次サイクルへ進む。"""

    clock = FakeClock()
    monitor = FakeMonitor(
        RealtimePollDecision.NO_NEW_BAR
    )

    original_poll = monitor.poll

    def flaky_poll(**kwargs):
        if monitor.calls == 0:
            monitor.calls += 1
            raise RuntimeError("temporary failure")

        return original_poll(**kwargs)

    monitor.poll = flaky_poll

    result = LiveTradingOrchestrator(
        market_monitor=monitor,
        paper_trading_service=FakePaperService(),
        now_provider=clock.now,
        sleeper=lambda _seconds: None,
    ).run(
        codes=("7203",),
        max_cycles=2,
        continue_on_error=True,
    )

    assert result.cycle_count == 2
    assert result.failed_cycle_count == 1
    assert result.completed_cycle_count == 1


def test_run_rejects_invalid_settings() -> None:
    """不正な運転設定を拒否する。"""

    orchestrator = LiveTradingOrchestrator(
        market_monitor=FakeMonitor(
            RealtimePollDecision.NO_NEW_BAR
        ),
        paper_trading_service=FakePaperService(),
    )

    with pytest.raises(ValueError, match="ポーリング"):
        orchestrator.run(
            codes=("7203",),
            poll_interval_seconds=-1,
            max_cycles=1,
        )

    with pytest.raises(ValueError, match="最大サイクル"):
        orchestrator.run(
            codes=("7203",),
            max_cycles=0,
        )

    with pytest.raises(ValueError, match="1件以上"):
        orchestrator.run(
            codes=(),
            max_cycles=1,
        )


def test_run_rejects_naive_clock() -> None:
    """タイムゾーンなし時計を拒否する。"""

    orchestrator = LiveTradingOrchestrator(
        market_monitor=FakeMonitor(
            RealtimePollDecision.NO_NEW_BAR
        ),
        paper_trading_service=FakePaperService(),
        now_provider=lambda: datetime(2026, 7, 17),
    )

    with pytest.raises(ValueError, match="タイムゾーン"):
        orchestrator.run(
            codes=("7203",),
            max_cycles=1,
        )
