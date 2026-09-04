"""Universe Daily Collectorの中間永続化テスト。"""

from datetime import date
from pathlib import Path

import pytest

from app.market.kabu_station_models import KabuStationSymbol
from app.universe.kabu_station_universe_daily_collector import (
    KabuStationUniverseDailyBarCollector,
)


class FakeSettings:
    maximum_registered_symbols = 2


class InterruptingClient:
    settings = FakeSettings()

    def __init__(self) -> None:
        self.board_calls = 0

    def issue_token(self) -> str:
        return "token"

    def unregister_all(self) -> None:
        return None

    def register_symbols(
        self,
        symbols: tuple[KabuStationSymbol, ...],
    ):
        return symbols

    def board(self, symbol: KabuStationSymbol):
        self.board_calls += 1
        if self.board_calls == 3:
            raise KeyboardInterrupt("simulated scheduler timeout")
        return {
            "OpeningPrice": 1000.0,
            "HighPrice": 1050.0,
            "LowPrice": 990.0,
            "CurrentPrice": 1030.0,
            "TradingVolume": 123456,
        }


class RecordingRepository:
    def __init__(self) -> None:
        self.saved_batches: list[tuple] = []

    def upsert_many(self, bars):
        batch = tuple(bars)
        self.saved_batches.append(batch)
        return len(batch)


def test_completed_symbols_are_persisted_before_later_interrupt(
    tmp_path: Path,
) -> None:
    repository = RecordingRepository()
    collector = KabuStationUniverseDailyBarCollector(
        client=InterruptingClient(),
        database_path=tmp_path / "katana.db",
        repository=repository,
        registration_batch_size=2,
        request_interval_seconds=0,
        retry_backoff_seconds=0,
        sleeper=lambda _seconds: None,
    )

    with pytest.raises(KeyboardInterrupt):
        collector.collect(
            trading_date=date(2026, 9, 3),
            codes=("1111", "2222", "3333", "4444"),
        )

    assert len(repository.saved_batches) == 2
    assert [len(batch) for batch in repository.saved_batches] == [1, 1]
    assert [
        batch[0].code for batch in repository.saved_batches
    ] == ["1111", "2222"]


def test_alphanumeric_jpx_code_is_preserved() -> None:
    normalized = KabuStationUniverseDailyBarCollector._normalize_codes(
        ("543A", "186a", "7203", "bad-code")
    )

    assert normalized == ("543A", "186A", "7203")
