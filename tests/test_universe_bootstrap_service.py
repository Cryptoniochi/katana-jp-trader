"""全市場Universe Bootstrapのテスト。"""

from datetime import date, datetime, timezone
from pathlib import Path

from app.universe.listed_symbol_repository import (
    ListedSymbolRepository,
)
from app.universe.universe_bootstrap_service import (
    UniverseBootstrapService,
)
from app.universe.universe_daily_bar_models import (
    UniverseDailyBar,
)
from app.universe.universe_daily_bar_repository import (
    UniverseDailyBarRepository,
)
from app.universe.kabu_station_universe_daily_collector import (
    UniverseDailyCollectionResult,
)
from app.universe.universe_models import ListedSymbol


NOW = datetime(
    2026,
    8,
    7,
    tzinfo=timezone.utc,
)
DAY = date(2026, 8, 7)


class FakeCollector:
    def __init__(
        self,
        database_path: Path,
        *,
        fail_codes: tuple[str, ...] = (),
    ) -> None:
        self.repository = UniverseDailyBarRepository(
            database_path
        )
        self.fail_codes = set(fail_codes)
        self.calls: list[tuple[str, ...]] = []

    def collect(
        self,
        *,
        trading_date: date,
        codes,
    ) -> UniverseDailyCollectionResult:
        normalized = tuple(codes)
        self.calls.append(normalized)

        successful = tuple(
            code
            for code in normalized
            if code not in self.fail_codes
        )
        bars = tuple(
            UniverseDailyBar(
                code=code,
                trading_date=trading_date,
                open_price=100.0,
                high_price=110.0,
                low_price=90.0,
                close_price=105.0,
                volume=1_000_000,
                data_source="test-bootstrap",
            )
            for code in successful
        )
        saved = self.repository.upsert_many(bars)

        return UniverseDailyCollectionResult(
            generated_at=NOW,
            trading_date=trading_date,
            requested_count=len(normalized),
            collected_count=len(successful),
            saved_count=saved,
            skips=(),
            failures=(),
            source_name="test-bootstrap",
            minimum_success_ratio=0.0,
        )


def seed_symbols(
    database_path: Path,
    codes: tuple[str, ...],
) -> None:
    repository = ListedSymbolRepository(
        database_path
    )
    repository.upsert_many(
        tuple(
            ListedSymbol(
                code=code,
                name=f"Name {code}",
                market="Prime",
                security_type="common_stock",
                trading_unit=100,
                listed_date=None,
                delisted_date=None,
                is_active=True,
                source="test",
                updated_at=NOW,
            )
            for code in codes
        )
    )


def test_bootstrap_runs_in_batches_and_resumes(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    seed_symbols(
        database,
        ("1306", "607A", "7203", "8306", "9432"),
    )
    collector = FakeCollector(database)
    service = UniverseBootstrapService(
        database_path=database,
        collector=collector,
        maximum_symbols_per_run=2,
        now_provider=lambda: NOW,
    )

    first = service.run_once(
        trading_date=DAY
    )
    second = service.run_once(
        trading_date=DAY
    )
    third = service.run_once(
        trading_date=DAY
    )
    fourth = service.run_once(
        trading_date=DAY
    )

    assert first.attempted_count == 2
    assert first.remaining_count == 3
    assert second.attempted_count == 2
    assert second.remaining_count == 1
    assert third.attempted_count == 1
    assert third.remaining_count == 0
    assert third.completed is True
    assert fourth.attempted_count == 0
    assert fourth.completed is True
    assert collector.calls == [
        ("1306", "607A"),
        ("7203", "8306"),
        ("9432",),
    ]


def test_failed_code_is_retried_next_run(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    seed_symbols(
        database,
        ("607A", "7203", "8306"),
    )
    collector = FakeCollector(
        database,
        fail_codes=("607A",),
    )
    service = UniverseBootstrapService(
        database_path=database,
        collector=collector,
        maximum_symbols_per_run=2,
        now_provider=lambda: NOW,
    )

    first = service.run_once(
        trading_date=DAY
    )

    assert "607A" in first.failed_codes
    assert first.remaining_count == 2

    collector.fail_codes.clear()
    second = service.run_once(
        trading_date=DAY
    )

    assert "607A" in second.selected_codes
    assert second.collected_count == 2
