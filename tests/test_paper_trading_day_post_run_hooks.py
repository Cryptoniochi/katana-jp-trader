"""PaperTradingDayServiceのPost-run Hook統合テスト。"""

from datetime import datetime, timezone

import pytest

from app.market.market_clock import (
    TokyoMarketClockSnapshot,
)
from app.market.market_session import (
    TokyoMarketSession,
)
from app.runtime.paper_trading_day_models import (
    PaperTradingDaySettings,
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
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeRuntime:
    def start(self) -> None:
        pass

    def run_cycle(self):
        raise AssertionError(
            "引け後テストではCycleは実行されません。"
        )

    def complete(self) -> PaperTradingDailySummary:
        return PaperTradingDailySummary(
            trading_date=NOW.date(),
            started_at=NOW,
            completed_at=NOW,
            status=PaperTradingRuntimeStatus.COMPLETED,
            records=(),
            initial_equity=1_000_000.0,
            final_equity=1_010_000.0,
        )

    def fail(
        self,
        *,
        error_message: str,
    ) -> PaperTradingDailySummary:
        raise AssertionError(error_message)


class FakeRecord:
    trading_date = NOW.date()
    status = PaperTradingRuntimeStatus.COMPLETED
    created_at = NOW
    updated_at = NOW


class FakePersistenceResult:
    record = FakeRecord()


class FakePersister:
    def persist(self, summary):
        return FakePersistenceResult()


class AfterCloseClock:
    def snapshot(
        self,
        observed_at: datetime,
    ) -> TokyoMarketClockSnapshot:
        return TokyoMarketClockSnapshot(
            observed_at=observed_at,
            local_at=observed_at,
            business_day=True,
            session=TokyoMarketSession.AFTER_CLOSE,
            next_trading_at=observed_at,
            wait_seconds=0.0,
        )


class FakeHook:
    def __init__(
        self,
        name: str,
        log: list[str],
        *,
        raises: bool = False,
    ) -> None:
        self.name = name
        self.log = log
        self.raises = raises

    def handle(self, result) -> None:
        self.log.append(self.name)

        if self.raises:
            raise RuntimeError(
                f"{self.name} failed"
            )


def create_service(
    *,
    hooks=(),
    continue_on_post_run_hook_error=True,
) -> PaperTradingDayService:
    return PaperTradingDayService(
        runtime=FakeRuntime(),
        persistence_service=FakePersister(),
        market_clock=AfterCloseClock(),
        post_run_hooks=hooks,
        settings=PaperTradingDaySettings(
            continue_on_post_run_hook_error=(
                continue_on_post_run_hook_error
            )
        ),
        now_provider=lambda: NOW,
        sleeper=lambda _seconds: None,
    )


def test_post_run_hooks_execute_in_order() -> None:
    log: list[str] = []
    service = create_service(
        hooks=(
            FakeHook("hook-1", log),
            FakeHook("hook-2", log),
        )
    )

    result = service.run()

    assert log == ["hook-1", "hook-2"]
    assert result.completed_post_run_hook_count == 2
    assert result.post_run_hook_failure_count == 0


def test_post_run_hook_error_is_recorded() -> None:
    log: list[str] = []
    service = create_service(
        hooks=(
            FakeHook(
                "hook-1",
                log,
                raises=True,
            ),
            FakeHook("hook-2", log),
        )
    )

    result = service.run()

    assert log == ["hook-1", "hook-2"]
    assert result.completed_post_run_hook_count == 1
    assert result.post_run_hook_error_messages == (
        "hook-1 failed",
    )


def test_post_run_hook_error_can_be_raised() -> None:
    log: list[str] = []
    service = create_service(
        hooks=(
            FakeHook(
                "hook-1",
                log,
                raises=True,
            ),
        ),
        continue_on_post_run_hook_error=False,
    )

    with pytest.raises(
        RuntimeError,
        match="hook-1 failed",
    ):
        service.run()
