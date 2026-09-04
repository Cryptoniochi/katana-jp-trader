import json
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
        self.settings = SimpleNamespace(
            maximum_registered_symbols=50,
            timeout_seconds=4.0,
        )
        self.calls: dict[str, int] = {}

    def issue_token(self):
        return "token"

    def unregister_all(self):
        return None

    def register_symbols(self, symbols):
        return tuple(symbols)

    def board(self, symbol, *, timeout_seconds=None):
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


def test_board_readiness_trace_is_persisted(tmp_path: Path):
    metrics_path = tmp_path / "board_metrics_latest.json"

    collector = KabuStationUniverseDailyBarCollector(
        client=FakeClient(),
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
        codes=("1111", "2222"),
    )

    assert result.collected_count == 2

    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    trace = payload["board_readiness_trace"]

    assert len(trace) == 3
    assert trace[0]["code"] == "1111"
    assert trace[0]["attempt"] == 1
    assert trace[0]["success"] is False
    assert trace[0]["timeout_like"] is True
    assert trace[0]["timeout_seconds"] == 0.75
    assert trace[0]["seconds_since_registration"] is not None

    assert trace[1]["code"] == "1111"
    assert trace[1]["attempt"] == 2
    assert trace[1]["success"] is True
    assert trace[1]["timeout_seconds"] == 4.0

    assert trace[2]["code"] == "2222"
    assert trace[2]["attempt"] == 1
    assert trace[2]["success"] is True

    profile = payload["first_attempt_readiness_profile"]
    assert profile
    assert sum(item["attempt_count"] for item in profile) == 2
    assert sum(item["success_count"] for item in profile) == 1
    assert sum(item["timeout_like_count"] for item in profile) == 1


def test_readiness_trace_does_not_change_collection_result(tmp_path: Path):
    collector = KabuStationUniverseDailyBarCollector(
        client=FakeClient(),
        database_path=Path("unused.db"),
        repository=FakeRepository(),
        request_interval_seconds=0,
        retry_backoff_seconds=0,
        sleeper=lambda _: None,
        metrics_report_path=tmp_path / "metrics.json",
    )

    result = collector.collect(
        trading_date=date(2026, 9, 4),
        codes=("2222",),
    )

    assert result.requested_count == 1
    assert result.collected_count == 1
    assert result.saved_count == 1
    assert not result.failures
