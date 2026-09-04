"""Sprint 131-4: successful registered symbols are persisted immediately."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.universe.kabu_station_universe_daily_collector import (
    KabuStationUniverseDailyBarCollector,
)


class FakeRepository:
    def __init__(self) -> None:
        self.calls = []

    def upsert_many(self, bars):
        bars = tuple(bars)
        self.calls.append(bars)
        return len(bars)


class FakeClient:
    settings = SimpleNamespace(maximum_registered_symbols=50)

    def issue_token(self):
        return None

    def unregister_all(self):
        return None

    def register_symbols(self, _symbols):
        return None

    def board(self, symbol):
        return {
            "OpeningPrice": 100.0,
            "HighPrice": 110.0,
            "LowPrice": 95.0,
            "CurrentPrice": 105.0,
            "TradingVolume": 1000,
        }


def test_registered_collection_persists_each_symbol_immediately(
    tmp_path: Path,
) -> None:
    repository = FakeRepository()
    collector = KabuStationUniverseDailyBarCollector(
        client=FakeClient(),
        database_path=tmp_path / "katana.db",
        repository=repository,
        request_interval_seconds=0,
        registration_batch_size=50,
    )

    result = collector.collect(
        trading_date=date(2026, 9, 3),
        codes=("1926", "1928", "192A"),
    )

    assert result.collected_count == 3
    assert result.saved_count == 3
    assert [len(call) for call in repository.calls] == [1, 1, 1]
    assert [
        call[0].code for call in repository.calls
    ] == ["1926", "1928", "192A"]
