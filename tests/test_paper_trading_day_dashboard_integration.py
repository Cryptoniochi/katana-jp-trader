"""PaperTradingDayServiceとDashboard公開の統合テスト。"""

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
    21,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeRuntime:
    """Dashboard統合テスト用Runtime。"""

    def start(self) -> None:
        pass

    def run_cycle(self):
        raise AssertionError(
            "引け後テストではCycleは実行されません。"
        )

    def complete(self) -> PaperTradingDailySummary:
        return self._summary(
            status=PaperTradingRuntimeStatus.COMPLETED,
        )

    def fail(
        self,
        *,
        error_message: str,
    ) -> PaperTradingDailySummary:
        return self._summary(
            status=PaperTradingRuntimeStatus.FAILED,
            error_message=error_message,
        )

    @staticmethod
    def _summary(
        *,
        status: PaperTradingRuntimeStatus,
        error_message: str | None = None,
    ) -> PaperTradingDailySummary:
        return PaperTradingDailySummary(
            trading_date=NOW.date(),
            started_at=NOW,
            completed_at=NOW,
            status=status,
            records=(),
            initial_equity=1_000_000.0,
            final_equity=1_010_000.0,
            error_message=error_message,
        )


class FakeRecord:
    """保存済み日次レコード。"""

    trading_date = NOW.date()
    status = PaperTradingRuntimeStatus.COMPLETED
    created_at = NOW
    updated_at = NOW


class FakePersistenceResult:
    """日次永続化結果。"""

    record = FakeRecord()


class FakePersister:
    """呼出順序を記録するPersister。"""

    def __init__(self, log: list[str]) -> None:
        self.log = log

    def persist(self, summary):
        self.log.append("persist")
        return FakePersistenceResult()


class FakeDashboardPublisher:
    """呼出順序を記録するDashboard Publisher。"""

    def __init__(
        self,
        log: list[str],
        *,
        raises: bool = False,
    ) -> None:
        self.log = log
        self.raises = raises

    def publish(self):
        self.log.append("publish")

        if self.raises:
            raise RuntimeError("dashboard failed")

        return object()


class AfterCloseClock:
    """常に引け後を返すMarket Clock。"""

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


def create_service(
    *,
    log: list[str],
    publisher,
    continue_on_dashboard_error: bool = True,
) -> PaperTradingDayService:
    """テスト対象Serviceを作成する。"""

    return PaperTradingDayService(
        runtime=FakeRuntime(),
        persistence_service=FakePersister(log),
        market_clock=AfterCloseClock(),
        dashboard_publisher=publisher,
        settings=PaperTradingDaySettings(
            continue_on_dashboard_error=(
                continue_on_dashboard_error
            )
        ),
        now_provider=lambda: NOW,
        sleeper=lambda _seconds: None,
    )


def test_dashboard_is_published_after_persistence() -> None:
    """日次保存後にDashboardを公開する。"""

    log: list[str] = []
    service = create_service(
        log=log,
        publisher=FakeDashboardPublisher(log),
    )

    result = service.run()

    assert log == ["persist", "publish"]
    assert result.dashboard_published is True
    assert result.dashboard_error_message is None


def test_dashboard_failure_does_not_lose_daily_result() -> None:
    """既定ではDashboard失敗を日次運用失敗へ波及させない。"""

    log: list[str] = []
    service = create_service(
        log=log,
        publisher=FakeDashboardPublisher(
            log,
            raises=True,
        ),
    )

    result = service.run()

    assert log == ["persist", "publish"]
    assert result.dashboard_published is False
    assert result.dashboard_error_message == (
        "dashboard failed"
    )
    assert result.record.trading_date == NOW.date()


def test_dashboard_failure_can_be_raised_strictly() -> None:
    """厳格設定ではDashboard公開失敗を送出する。"""

    log: list[str] = []
    service = create_service(
        log=log,
        publisher=FakeDashboardPublisher(
            log,
            raises=True,
        ),
        continue_on_dashboard_error=False,
    )

    with pytest.raises(
        RuntimeError,
        match="dashboard failed",
    ):
        service.run()

    assert log == ["persist", "publish"]
