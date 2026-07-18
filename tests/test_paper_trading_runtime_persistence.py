"""PaperTradingRuntimePersistenceServiceのテスト。"""

from datetime import datetime, timezone

from app.runtime.paper_trading_daily_repository import (
    PaperTradingDailySummaryRepository,
)
from app.runtime.paper_trading_persistence_service import (
    PaperTradingPersistenceService,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingDailySummary,
    PaperTradingRuntimeStatus,
)
from app.runtime.paper_trading_runtime_persistence import (
    PaperTradingRuntimePersistenceService,
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
        return PaperTradingDailySummary(
            trading_date=NOW.date(),
            started_at=NOW,
            completed_at=NOW,
            status=PaperTradingRuntimeStatus.FAILED,
            records=(),
            initial_equity=1_000_000.0,
            final_equity=990_000.0,
            error_message=error_message,
        )


def create_service(tmp_path):
    repository = PaperTradingDailySummaryRepository(
        tmp_path / "katana.db",
        now_provider=lambda: NOW,
    )
    persistence = PaperTradingPersistenceService(
        daily_repository=repository
    )
    service = PaperTradingRuntimePersistenceService(
        runtime=FakeRuntime(),
        persistence_service=persistence,
    )
    return service, repository


def test_complete_and_persist(
    tmp_path,
) -> None:
    service, repository = create_service(tmp_path)

    result = service.complete_and_persist()

    assert result.summary.status is (
        PaperTradingRuntimeStatus.COMPLETED
    )
    assert repository.count() == 1


def test_fail_and_persist(
    tmp_path,
) -> None:
    service, repository = create_service(tmp_path)

    result = service.fail_and_persist(
        error_message="runtime failed"
    )
    loaded = repository.get(NOW.date())

    assert result.summary.status is (
        PaperTradingRuntimeStatus.FAILED
    )
    assert loaded is not None
    assert loaded.error_message == "runtime failed"
    assert loaded.net_profit_loss == -10_000.0
