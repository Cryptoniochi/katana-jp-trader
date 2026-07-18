"""PaperTradingDailySummaryRepositoryのテスト。"""

from datetime import datetime, timezone

import pytest

from app.runtime.paper_trading_daily_repository import (
    PaperTradingDailySummaryRepository,
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


def summary(
    *,
    final_equity: float = 1_010_000.0,
) -> PaperTradingDailySummary:
    return PaperTradingDailySummary(
        trading_date=NOW.date(),
        started_at=NOW,
        completed_at=NOW,
        status=PaperTradingRuntimeStatus.COMPLETED,
        records=(),
        initial_equity=1_000_000.0,
        final_equity=final_equity,
    )


def test_repository_saves_and_gets_summary(
    tmp_path,
) -> None:
    repository = PaperTradingDailySummaryRepository(
        tmp_path / "katana.db",
        now_provider=lambda: NOW,
    )

    saved = repository.save(summary())
    loaded = repository.get(NOW.date())

    assert saved.trading_date == NOW.date()
    assert loaded is not None
    assert loaded.status is (
        PaperTradingRuntimeStatus.COMPLETED
    )
    assert loaded.net_profit_loss == 10_000.0
    assert loaded.return_rate == pytest.approx(0.01)
    assert loaded.payload["status"] == "completed"
    assert repository.count() == 1


def test_repository_upserts_same_trading_date(
    tmp_path,
) -> None:
    repository = PaperTradingDailySummaryRepository(
        tmp_path / "katana.db",
        now_provider=lambda: NOW,
    )

    repository.save(summary())
    repository.save(
        summary(final_equity=1_020_000.0)
    )

    loaded = repository.get(NOW.date())

    assert repository.count() == 1
    assert loaded is not None
    assert loaded.net_profit_loss == 20_000.0
    assert loaded.final_equity == 1_020_000.0


def test_repository_lists_recent_records(
    tmp_path,
) -> None:
    repository = PaperTradingDailySummaryRepository(
        tmp_path / "katana.db",
        now_provider=lambda: NOW,
    )
    first = summary()
    second = PaperTradingDailySummary(
        trading_date=NOW.date().replace(day=19),
        started_at=NOW.replace(day=19),
        completed_at=NOW.replace(day=19),
        status=PaperTradingRuntimeStatus.COMPLETED,
        records=(),
        initial_equity=1_010_000.0,
        final_equity=1_015_000.0,
    )

    repository.save(first)
    repository.save(second)

    records = repository.list_recent(limit=2)

    assert [
        item.trading_date.isoformat()
        for item in records
    ] == [
        "2026-07-19",
        "2026-07-18",
    ]
