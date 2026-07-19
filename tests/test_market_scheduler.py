"""MarketSchedulerの市場時間・待機・終了制御テスト。"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.live.live_orchestrator_models import (
    LiveCycleResult,
    LiveCycleStatus,
)
from app.live.market_scheduler import (
    MarketScheduler,
)
from app.live.market_scheduler_models import (
    MarketSchedulerSettings,
    MarketSchedulerStopReason,
)
from app.market.realtime_market_service import (
    JST,
    TokyoMarketSessionService,
)
from app.market.realtime_models import (
    MarketSessionSnapshot,
    MarketSessionState,
    RealtimeMarketPollResult,
    RealtimePollDecision,
)


UTC = ZoneInfo("UTC")


def market_result(
    observed_at: datetime,
) -> RealtimeMarketPollResult:
    """空の市場監視結果を作成する。"""

    local_time = observed_at.astimezone(JST)

    return RealtimeMarketPollResult(
        session=MarketSessionSnapshot(
            observed_at=local_time,
            trading_date=local_time.date(),
            is_trading_day=True,
            state=MarketSessionState.MORNING,
        ),
        decision=RealtimePollDecision.NO_NEW_BAR,
        code_count=1,
        fetched_bar_count=0,
        new_bar_count=0,
        saved_bar_count=0,
        new_bars=(),
    )


class FakeClock:
    """sleepに応じて進むテスト用時計。"""

    def __init__(
        self,
        current: datetime,
    ) -> None:
        self.current = current

    def now(self) -> datetime:
        """現在日時を返す。"""

        return self.current

    def sleep(self, seconds: float) -> None:
        """指定秒数だけ現在日時を進める。"""

        self.current += timedelta(
            seconds=seconds
        )


class FakeOrchestrator:
    """取引サイクル呼出を記録する。"""

    def __init__(self) -> None:
        self.calls: list[
            tuple[int, tuple[str, ...], bool]
        ] = []
        self.raise_error = False
        self.return_failed = False

    def run_cycle(
        self,
        *,
        cycle_number: int,
        codes,
        continue_on_error: bool = True,
    ) -> LiveCycleResult:
        """テスト用取引サイクル結果を返す。"""

        normalized_codes = tuple(codes)

        self.calls.append(
            (
                cycle_number,
                normalized_codes,
                continue_on_error,
            )
        )

        if self.raise_error:
            raise RuntimeError(
                "orchestrator failed"
            )

        started_at = datetime(
            2026,
            7,
            17,
            0,
            cycle_number,
            tzinfo=UTC,
        )

        if self.return_failed:
            return LiveCycleResult(
                cycle_number=cycle_number,
                started_at=started_at,
                completed_at=started_at,
                status=LiveCycleStatus.FAILED,
                market_result=None,
                paper_trading_result=None,
                error_message="cycle failed",
            )

        return LiveCycleResult(
            cycle_number=cycle_number,
            started_at=started_at,
            completed_at=started_at,
            status=LiveCycleStatus.COMPLETED,
            market_result=market_result(
                started_at
            ),
            paper_trading_result=None,
            error_message=None,
        )


def session_service(
    *,
    trading_day: bool = True,
) -> TokyoMarketSessionService:
    """固定した取引日判定を持つサービスを返す。"""

    return TokyoMarketSessionService(
        trading_day_predicate=(
            lambda _date: trading_day
        )
    )


def test_scheduler_does_not_run_on_non_trading_day() -> None:
    """非取引日はOrchestratorを実行せず終了する。"""

    clock = FakeClock(
        datetime(
            2026,
            7,
            18,
            9,
            0,
            tzinfo=JST,
        )
    )
    orchestrator = FakeOrchestrator()

    result = MarketScheduler(
        orchestrator=orchestrator,
        session_service=session_service(
            trading_day=False
        ),
        now_provider=clock.now,
        sleeper=clock.sleep,
    ).run(
        codes=("7203",),
    )

    assert result.stop_reason is (
        MarketSchedulerStopReason.NON_TRADING_DAY
    )
    assert result.cycle_count == 0
    assert result.sleep_count == 0
    assert orchestrator.calls == []


def test_scheduler_waits_until_market_open() -> None:
    """寄付前は9時まで待機して取引を開始する。"""

    clock = FakeClock(
        datetime(
            2026,
            7,
            17,
            8,
            58,
            tzinfo=JST,
        )
    )
    orchestrator = FakeOrchestrator()

    result = MarketScheduler(
        orchestrator=orchestrator,
        session_service=session_service(),
        now_provider=clock.now,
        sleeper=clock.sleep,
    ).run(
        codes=("7203",),
        settings=MarketSchedulerSettings(
            trading_poll_interval_seconds=30.0,
            idle_poll_interval_seconds=60.0,
            max_cycles=1,
        ),
    )

    assert result.stop_reason is (
        MarketSchedulerStopReason.MAX_CYCLES_REACHED
    )
    assert result.cycle_count == 1
    assert result.sleep_count == 2
    assert result.slept_seconds == pytest.approx(
        120.0
    )
    assert orchestrator.calls == [
        (
            1,
            ("7203",),
            True,
        )
    ]


def test_scheduler_runs_cycles_during_market_hours() -> None:
    """取引時間中は指定間隔でサイクルを実行する。"""

    clock = FakeClock(
        datetime(
            2026,
            7,
            17,
            9,
            0,
            tzinfo=JST,
        )
    )
    orchestrator = FakeOrchestrator()

    result = MarketScheduler(
        orchestrator=orchestrator,
        session_service=session_service(),
        now_provider=clock.now,
        sleeper=clock.sleep,
    ).run(
        codes=("7203", "6758", "7203"),
        settings=MarketSchedulerSettings(
            trading_poll_interval_seconds=30.0,
            max_cycles=3,
        ),
    )

    assert result.stop_reason is (
        MarketSchedulerStopReason.MAX_CYCLES_REACHED
    )
    assert result.cycle_count == 3
    assert result.completed_cycle_count == 3
    assert result.sleep_count == 2
    assert result.slept_seconds == pytest.approx(
        60.0
    )

    assert [
        call[0]
        for call in orchestrator.calls
    ] == [1, 2, 3]

    assert all(
        call[1] == ("7203", "6758")
        for call in orchestrator.calls
    )


def test_scheduler_waits_during_lunch_break() -> None:
    """昼休みは12時30分まで待機する。"""

    clock = FakeClock(
        datetime(
            2026,
            7,
            17,
            12,
            28,
            tzinfo=JST,
        )
    )
    orchestrator = FakeOrchestrator()

    result = MarketScheduler(
        orchestrator=orchestrator,
        session_service=session_service(),
        now_provider=clock.now,
        sleeper=clock.sleep,
    ).run(
        codes=("7203",),
        settings=MarketSchedulerSettings(
            idle_poll_interval_seconds=60.0,
            max_cycles=1,
        ),
    )

    assert result.stop_reason is (
        MarketSchedulerStopReason.MAX_CYCLES_REACHED
    )
    assert result.cycle_count == 1
    assert result.sleep_count == 2
    assert result.slept_seconds == pytest.approx(
        120.0
    )


def test_scheduler_stops_after_market_close() -> None:
    """大引け後は取引せず正常終了する。"""

    clock = FakeClock(
        datetime(
            2026,
            7,
            17,
            15,
            30,
            tzinfo=JST,
        )
    )
    orchestrator = FakeOrchestrator()

    result = MarketScheduler(
        orchestrator=orchestrator,
        session_service=session_service(),
        now_provider=clock.now,
        sleeper=clock.sleep,
    ).run(
        codes=("7203",),
    )

    assert result.stop_reason is (
        MarketSchedulerStopReason.MARKET_CLOSED
    )
    assert result.cycle_count == 0
    assert orchestrator.calls == []


def test_scheduler_stops_when_requested() -> None:
    """外部停止要求で安全に終了する。"""

    clock = FakeClock(
        datetime(
            2026,
            7,
            17,
            9,
            0,
            tzinfo=JST,
        )
    )
    orchestrator = FakeOrchestrator()

    result = MarketScheduler(
        orchestrator=orchestrator,
        session_service=session_service(),
        now_provider=clock.now,
        sleeper=clock.sleep,
        stop_requested=lambda: True,
    ).run(
        codes=("7203",),
    )

    assert result.stop_reason is (
        MarketSchedulerStopReason.STOP_REQUESTED
    )
    assert result.cycle_count == 0
    assert orchestrator.calls == []


def test_scheduler_converts_orchestrator_error_to_result() -> None:
    """Orchestrator例外をエラー終了結果へ変換する。"""

    clock = FakeClock(
        datetime(
            2026,
            7,
            17,
            9,
            0,
            tzinfo=JST,
        )
    )
    orchestrator = FakeOrchestrator()
    orchestrator.raise_error = True

    result = MarketScheduler(
        orchestrator=orchestrator,
        session_service=session_service(),
        now_provider=clock.now,
        sleeper=clock.sleep,
    ).run(
        codes=("7203",),
        settings=MarketSchedulerSettings(
            continue_on_error=False,
        ),
    )

    assert result.stop_reason is (
        MarketSchedulerStopReason.ERROR
    )
    assert result.was_stopped_by_error
    assert result.error_message == (
        "orchestrator failed"
    )
    assert result.cycle_count == 0


def test_scheduler_accepts_failed_cycle_in_continue_mode() -> None:
    """継続モードでは失敗サイクル後も次へ進む。"""

    clock = FakeClock(
        datetime(
            2026,
            7,
            17,
            9,
            0,
            tzinfo=JST,
        )
    )
    orchestrator = FakeOrchestrator()
    orchestrator.return_failed = True

    result = MarketScheduler(
        orchestrator=orchestrator,
        session_service=session_service(),
        now_provider=clock.now,
        sleeper=clock.sleep,
    ).run(
        codes=("7203",),
        settings=MarketSchedulerSettings(
            trading_poll_interval_seconds=1.0,
            max_cycles=2,
            continue_on_error=True,
        ),
    )

    assert result.stop_reason is (
        MarketSchedulerStopReason.MAX_CYCLES_REACHED
    )
    assert result.cycle_count == 2
    assert result.failed_cycle_count == 2


def test_scheduler_rejects_invalid_settings() -> None:
    """不正な設定値を拒否する。"""

    with pytest.raises(
        ValueError,
        match="取引時間中",
    ):
        MarketSchedulerSettings(
            trading_poll_interval_seconds=-1.0
        )

    with pytest.raises(
        ValueError,
        match="待機中",
    ):
        MarketSchedulerSettings(
            idle_poll_interval_seconds=0.0
        )

    with pytest.raises(
        ValueError,
        match="最大サイクル",
    ):
        MarketSchedulerSettings(
            max_cycles=0
        )


def test_scheduler_rejects_invalid_codes() -> None:
    """空または不正な銘柄コードを拒否する。"""

    clock = FakeClock(
        datetime(
            2026,
            7,
            17,
            9,
            0,
            tzinfo=JST,
        )
    )
    scheduler = MarketScheduler(
        orchestrator=FakeOrchestrator(),
        session_service=session_service(),
        now_provider=clock.now,
        sleeper=clock.sleep,
    )

    with pytest.raises(
        ValueError,
        match="1件以上",
    ):
        scheduler.run(
            codes=(),
        )

    with pytest.raises(
        ValueError,
        match="数字",
    ):
        scheduler.run(
            codes=("ABCD",),
        )


def test_scheduler_rejects_naive_clock() -> None:
    """タイムゾーンなし現在日時を拒否する。"""

    scheduler = MarketScheduler(
        orchestrator=FakeOrchestrator(),
        session_service=session_service(),
        now_provider=lambda: datetime(
            2026,
            7,
            17,
            9,
            0,
        ),
    )

    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        scheduler.run(
            codes=("7203",),
        )