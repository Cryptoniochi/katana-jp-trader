"""PaperTradingPersistenceServiceのテスト。"""

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


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_service_persists_summary(
    tmp_path,
) -> None:
    repository = PaperTradingDailySummaryRepository(
        tmp_path / "katana.db",
        now_provider=lambda: NOW,
    )
    service = PaperTradingPersistenceService(
        daily_repository=repository
    )
    summary = PaperTradingDailySummary(
        trading_date=NOW.date(),
        started_at=NOW,
        completed_at=NOW,
        status=PaperTradingRuntimeStatus.COMPLETED,
        records=(),
        initial_equity=1_000_000.0,
        final_equity=1_005_000.0,
    )

    result = service.persist(summary)

    assert result.summary == summary
    assert result.trading_date == NOW.date()
    assert result.record.net_profit_loss == 5_000.0
