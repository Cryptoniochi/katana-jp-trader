from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.universe.kabu_station_universe_daily_collector import (
    KabuStationUniverseDailyBarCollector,
)


class FakeRepository:
    def upsert_many(self, bars):
        return len(tuple(bars))


class TimeoutAwareFakeClient:
    def __init__(self):
        self.settings = SimpleNamespace(
            maximum_registered_symbols=50,
            timeout_seconds=4.0,
        )
        self.board_timeouts = []
        self.calls = 0

    def issue_token(self):
        return "token"

    def register_symbols(self, symbols):
        return tuple(symbols)

    def unregister_all(self):
        return None

    def board(self, symbol, *, timeout_seconds=None):
        self.calls += 1
        self.board_timeouts.append(timeout_seconds)
        if self.calls == 1:
            raise TimeoutError("timed out")
        return {
            "OpeningPrice": 100,
            "HighPrice": 110,
            "LowPrice": 95,
            "CurrentPrice": 105,
            "TradingVolume": 1000,
        }


def test_first_board_attempt_uses_short_timeout_and_retry_uses_default(
    tmp_path: Path,
):
    client = TimeoutAwareFakeClient()
    metrics_path = tmp_path / "metrics.json"

    collector = KabuStationUniverseDailyBarCollector(
        client=client,
        database_path=Path("unused.db"),
        repository=FakeRepository(),
        request_interval_seconds=0,
        retry_backoff_seconds=0,
        sleeper=lambda _: None,
        metrics_report_path=metrics_path,
        board_first_attempt_timeout_seconds=0.75,
    )

    result = collector.collect(
        trading_date=date(2026, 9, 4),
        codes=("7203",),
    )

    assert result.collected_count == 1
    assert client.board_timeouts == [0.75, None]
    assert collector.board_metrics.first_attempt_count == 1
    assert collector.board_metrics.retry_attempt_count == 1
    assert collector.board_metrics.retry_success_count == 1


def test_first_board_timeout_must_be_positive():
    client = TimeoutAwareFakeClient()

    try:
        KabuStationUniverseDailyBarCollector(
            client=client,
            database_path=Path("unused.db"),
            repository=FakeRepository(),
            board_first_attempt_timeout_seconds=0,
        )
    except ValueError as error:
        assert "0より大きい" in str(error)
    else:
        raise AssertionError("ValueError was not raised")
