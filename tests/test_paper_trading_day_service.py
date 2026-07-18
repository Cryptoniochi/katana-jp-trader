"""PaperTradingDayServiceのテスト。"""

from datetime import datetime, timezone

from app.application.trading_loop_models import (
    TradingLoopCycleStatus,
)
from app.market.market_clock import (
    TokyoMarketClockSnapshot,
)
from app.market.market_session import (
    TokyoMarketSession,
)
from app.runtime.paper_trading_day_models import (
    PaperTradingDaySettings,
    PaperTradingDayStopReason,
)
from app.runtime.paper_trading_day_service import (
    PaperTradingDayService,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingDailySummary,
    PaperTradingRuntimeStatus,
)


NOW = datetime(
    2026,
    7,
    21,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeCycleResult:
    def __init__(
        self,
        number: int,
        status: TradingLoopCycleStatus,
    ) -> None:
        self.cycle_number = number
        self.status = status
        self.error_message = (
            "failed"
            if status is TradingLoopCycleStatus.FAILED
            else None
        )

    @property
    def is_successful(self) -> bool:
        return self.status is TradingLoopCycleStatus.COMPLETED

    @property
    def signal_count(self) -> int:
        return 0

    @property
    def execution_count(self) -> int:
        return 0


class FakeCycleRecord:
    def __init__(
        self,
        cycle_result: FakeCycleResult,
    ) -> None:
        self.cycle_result = cycle_result


class FakeRuntime:
    def __init__(
        self,
        statuses=(
            TradingLoopCycleStatus.COMPLETED,
        ),
        *,
        raises: bool = False,
    ) -> None:
        self.statuses = list(statuses)
        self.raises = raises
        self.calls = 0
        self.started = False
        self.failed_message = None

    def start(self) -> None:
        self.started = True

    def run_cycle(self):
        self.calls += 1

        if self.raises:
            raise RuntimeError("runtime error")

        return FakeCycleRecord(
            FakeCycleResult(
                self.calls,
                self.statuses[self.calls - 1],
            )
        )

    def complete(self) -> PaperTradingDailySummary:
        return self._summary(
            PaperTradingRuntimeStatus.COMPLETED
        )

    def fail(
        self,
        *,
        error_message: str,
    ) -> PaperTradingDailySummary:
        self.failed_message = error_message
        return self._summary(
            PaperTradingRuntimeStatus.FAILED,
            error_message=error_message,
        )

    def _summary(
        self,
        status,
        *,
        error_message=None,
    ) -> PaperTradingDailySummary:
        return PaperTradingDailySummary(
            trading_date=NOW.date(),
            started_at=NOW,
            completed_at=NOW,
            status=status,
            records=(),
            initial_equity=1_000_000.0,
            final_equity=1_000_000.0,
            error_message=error_message,
        )


class FakeRecord:
    trading_date = NOW.date()
    status = PaperTradingRuntimeStatus.COMPLETED
    created_at = NOW
    updated_at = NOW


class FakePersistenceResult:
    def __init__(self, summary) -> None:
        self.summary = summary
        self.record = FakeRecord()


class FakePersister:
    def __init__(self) -> None:
        self.summaries = []

    def persist(self, summary):
        self.summaries.append(summary)
        return FakePersistenceResult(summary)


class SequenceClock:
    def __init__(self, sessions) -> None:
        self.sessions = list(sessions)
        self.calls = 0

    def snapshot(self, observed_at):
        index = min(
            self.calls,
            len(self.sessions) - 1,
        )
        session = self.sessions[index]
        self.calls += 1
        return TokyoMarketClockSnapshot(
            observed_at=observed_at,
            local_at=observed_at,
            business_day=True,
            session=session,
            next_trading_at=observed_at,
            wait_seconds=60.0,
        )


def test_day_service_runs_until_market_close() -> None:
    runtime = FakeRuntime()
    persister = FakePersister()
    sleeps = []
    service = PaperTradingDayService(
        runtime=runtime,
        persistence_service=persister,
        market_clock=SequenceClock(
            (
                TokyoMarketSession.MORNING,
                TokyoMarketSession.AFTER_CLOSE,
            )
        ),
        settings=PaperTradingDaySettings(
            cycle_interval_seconds=5.0
        ),
        now_provider=lambda: NOW,
        sleeper=sleeps.append,
    )

    result = service.run()

    assert runtime.started
    assert runtime.calls == 1
    assert result.stop_reason is (
        PaperTradingDayStopReason.MARKET_CLOSED
    )
    assert len(persister.summaries) == 1
    assert sleeps == [5.0]


def test_day_service_waits_during_lunch() -> None:
    runtime = FakeRuntime()
    sleeps = []
    service = PaperTradingDayService(
        runtime=runtime,
        persistence_service=FakePersister(),
        market_clock=SequenceClock(
            (
                TokyoMarketSession.LUNCH,
                TokyoMarketSession.AFTER_CLOSE,
            )
        ),
        now_provider=lambda: NOW,
        sleeper=sleeps.append,
    )

    result = service.run()

    assert result.stop_reason is (
        PaperTradingDayStopReason.MARKET_CLOSED
    )
    assert runtime.calls == 0
    assert sleeps == [60.0]


def test_day_service_stops_on_resource_critical() -> None:
    runtime = FakeRuntime(
        statuses=(
            TradingLoopCycleStatus.RESOURCE_CRITICAL,
        )
    )
    service = PaperTradingDayService(
        runtime=runtime,
        persistence_service=FakePersister(),
        market_clock=SequenceClock(
            (TokyoMarketSession.MORNING,)
        ),
        settings=PaperTradingDaySettings(
            stop_on_resource_critical=True
        ),
        now_provider=lambda: NOW,
        sleeper=lambda _seconds: None,
    )

    result = service.run()

    assert result.stop_reason is (
        PaperTradingDayStopReason.RESOURCE_CRITICAL
    )


def test_day_service_persists_failed_summary_on_error() -> None:
    runtime = FakeRuntime(raises=True)
    persister = FakePersister()
    service = PaperTradingDayService(
        runtime=runtime,
        persistence_service=persister,
        market_clock=SequenceClock(
            (TokyoMarketSession.MORNING,)
        ),
        now_provider=lambda: NOW,
    )

    result = service.run()

    assert result.stop_reason is (
        PaperTradingDayStopReason.ERROR
    )
    assert result.error_message == "runtime error"
    assert runtime.failed_message == "runtime error"
    assert persister.summaries[0].status is (
        PaperTradingRuntimeStatus.FAILED
    )
