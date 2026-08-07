"""全市場Universe Bootstrap終端Skipのテスト。"""

from datetime import date, datetime, timezone
from pathlib import Path

from app.universe.kabu_station_universe_daily_collector import (
    UniverseDailyCollectionFailure,
    UniverseDailyCollectionResult,
    UniverseDailyCollectionSkip,
)
from app.universe.listed_symbol_repository import ListedSymbolRepository
from app.universe.universe_bootstrap_service import UniverseBootstrapService
from app.universe.universe_daily_bar_models import UniverseDailyBar
from app.universe.universe_daily_bar_repository import UniverseDailyBarRepository
from app.universe.universe_models import ListedSymbol


NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)
DAY = date(2026, 8, 7)


class FakeCollector:
    def __init__(self, database_path: Path) -> None:
        self.repository = UniverseDailyBarRepository(database_path)
        self.calls: list[tuple[str, ...]] = []

    def collect(self, *, trading_date: date, codes):
        normalized = tuple(codes)
        self.calls.append(normalized)
        bars = []
        skips = []
        failures = []

        for code in normalized:
            if code == "1795":
                skips.append(
                    UniverseDailyCollectionSkip(
                        code=code,
                        reason=(
                            "Board応答の値がありません: OpeningPrice"
                        ),
                    )
                )
                continue

            if code == "6197":
                failures.append(
                    UniverseDailyCollectionFailure(
                        code=code,
                        error_type="RuntimeError",
                        message=(
                            "銘柄登録不可: 4001018 銘柄が登録できませんでした"
                        ),
                        attempts=3,
                    )
                )
                continue

            bars.append(
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
            )

        saved = self.repository.upsert_many(tuple(bars))
        return UniverseDailyCollectionResult(
            generated_at=NOW,
            trading_date=trading_date,
            requested_count=len(normalized),
            collected_count=len(bars),
            saved_count=saved,
            skips=tuple(skips),
            failures=tuple(failures),
            source_name="test-bootstrap",
            minimum_success_ratio=0.0,
        )


def seed_symbols(database_path: Path, codes: tuple[str, ...]) -> None:
    ListedSymbolRepository(database_path).upsert_many(
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


def test_terminal_skips_are_persisted_and_not_retried(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    unavailable = tmp_path / "unavailable.json"
    seed_symbols(database, ("1795", "2152", "6197", "7203"))

    collector = FakeCollector(database)
    service = UniverseBootstrapService(
        database_path=database,
        collector=collector,
        maximum_symbols_per_run=10,
        minimum_completion_ratio=0.5,
        unavailable_path=unavailable,
        now_provider=lambda: NOW,
    )

    first = service.run_once(trading_date=DAY)
    assert first.remaining_count == 2
    assert first.retryable_remaining_count == 0
    assert first.terminal_skipped_count == 2
    assert first.completed is True

    second = service.run_once(trading_date=DAY)
    assert second.attempted_count == 0
    assert collector.calls == [
        ("1795", "2152", "6197", "7203")
    ]


def test_transient_failure_remains_retryable(tmp_path: Path) -> None:
    database = tmp_path / "katana.db"
    unavailable = tmp_path / "unavailable.json"
    seed_symbols(database, ("7203", "8306"))

    class TransientCollector(FakeCollector):
        def collect(self, *, trading_date: date, codes):
            normalized = tuple(codes)
            self.calls.append(normalized)
            return UniverseDailyCollectionResult(
                generated_at=NOW,
                trading_date=trading_date,
                requested_count=len(normalized),
                collected_count=0,
                saved_count=0,
                skips=(),
                failures=(
                    UniverseDailyCollectionFailure(
                        code="7203",
                        error_type="KabuStationConnectionError",
                        message="timed out",
                        attempts=3,
                    ),
                ),
                source_name="test-bootstrap",
                minimum_success_ratio=0.0,
            )

    collector = TransientCollector(database)
    service = UniverseBootstrapService(
        database_path=database,
        collector=collector,
        maximum_symbols_per_run=2,
        minimum_completion_ratio=0.99,
        unavailable_path=unavailable,
        now_provider=lambda: NOW,
    )

    result = service.run_once(trading_date=DAY)
    assert result.remaining_count == 2
    assert result.retryable_remaining_count == 2
    assert result.terminal_skipped_count == 0
    assert result.completed is False
