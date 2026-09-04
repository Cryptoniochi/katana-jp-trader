from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.universe.kabu_station_universe_daily_collector import (
    KabuStationUniverseDailyBarCollector,
)


class FakeRepository:
    def upsert_many(self, bars):
        return len(tuple(bars))


class FakeClient:
    def __init__(self):
        self.settings = SimpleNamespace(maximum_registered_symbols=50)
        self.calls = {}

    def issue_token(self):
        return "token"

    def unregister_all(self):
        return None

    def register_symbols(self, symbols):
        return tuple(symbols)

    def board(self, symbol):
        count = self.calls.get(symbol.code, 0) + 1
        self.calls[symbol.code] = count
        if symbol.code == "1111" and count == 1:
            raise TimeoutError("timed out")
        return {
            "OpeningPrice": 100,
            "HighPrice": 110,
            "LowPrice": 95,
            "CurrentPrice": 105,
            "TradingVolume": 1000,
        }


def test_board_metrics_capture_first_attempt_and_retry():
    messages = []
    collector = KabuStationUniverseDailyBarCollector(
        client=FakeClient(),
        database_path=Path("unused.db"),
        repository=FakeRepository(),
        request_interval_seconds=0,
        retry_backoff_seconds=0,
        sleeper=lambda _seconds: None,
        progress_reporter=messages.append,
    )

    result = collector.collect(
        trading_date=date(2026, 9, 4),
        codes=("1111", "2222"),
    )

    metrics = collector.board_metrics
    assert result.collected_count == 2
    assert metrics.request_count == 3
    assert metrics.first_attempt_count == 2
    assert metrics.first_attempt_success_count == 1
    assert metrics.retry_attempt_count == 1
    assert metrics.retry_success_count == 1
    assert metrics.timeout_like_count == 1
    assert metrics.failed_symbol_count == 0
    assert any(message.startswith("BOARD METRICS ") for message in messages)
