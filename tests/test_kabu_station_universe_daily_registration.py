"""Universe Daily Collectorの登録バッチ処理テスト。"""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.universe.kabu_station_universe_daily_collector import (
    KabuStationUniverseDailyBarCollector,
)


class FakeClient:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            maximum_registered_symbols=2
        )
        self.registered = set()
        self.register_calls = []
        self.unregister_count = 0

    def issue_token(self):
        return "token"

    def register_symbols(self, symbols):
        normalized = tuple(symbols)
        self.register_calls.append(
            tuple(symbol.code for symbol in normalized)
        )
        self.registered = {
            symbol.code
            for symbol in normalized
        }
        return normalized

    def unregister_all(self):
        self.unregister_count += 1
        self.registered = set()

    def board(self, symbol):
        if symbol.code not in self.registered:
            raise RuntimeError("レジスト数エラー")

        return {
            "OpeningPrice": 100.0,
            "HighPrice": 110.0,
            "LowPrice": 90.0,
            "CurrentPrice": 105.0,
            "TradingVolume": 1000.0,
        }


class FakeRepository:
    def __init__(self) -> None:
        self.saved = ()

    def upsert_many(self, bars):
        self.saved = bars
        return len(bars)


def test_collects_in_registration_batches(
    tmp_path: Path,
) -> None:
    client = FakeClient()
    repository = FakeRepository()
    collector = KabuStationUniverseDailyBarCollector(
        client=client,
        database_path=tmp_path / "katana.db",
        repository=repository,
        request_interval_seconds=0,
        retry_backoff_seconds=0,
        sleeper=lambda _seconds: None,
    )

    result = collector.collect(
        trading_date=date(2026, 8, 6),
        codes=("1306", "1332", "1605", "1801", "1802"),
    )

    assert result.completed is True
    assert result.collected_count == 5
    assert result.saved_count == 5
    assert client.register_calls == [
        ("1306", "1332"),
        ("1605", "1801"),
        ("1802",),
    ]
    assert client.registered == set()
    assert client.unregister_count >= 3
