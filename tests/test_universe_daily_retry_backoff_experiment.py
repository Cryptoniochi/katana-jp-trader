import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.run_universe_bootstrap import build_argument_parser
from app.universe.kabu_station_universe_daily_collector import (
    KabuStationUniverseDailyBarCollector,
)


class FakeRepository:
    def __init__(self):
        self.saved = []

    def upsert_many(self, bars):
        values = tuple(bars)
        self.saved.extend(values)
        return len(values)


class RetryClient:
    def __init__(self):
        self.settings = SimpleNamespace(
            maximum_registered_symbols=50,
            timeout_seconds=4.0,
        )
        self.calls = 0

    def issue_token(self):
        return "token"

    def register_symbols(self, symbols):
        return tuple(symbols)

    def unregister_all(self):
        return None

    def board(self, symbol, *, timeout_seconds=None):
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("timed out")
        return {
            "OpeningPrice": 100,
            "HighPrice": 110,
            "LowPrice": 95,
            "CurrentPrice": 105,
            "TradingVolume": 1000,
        }


class RecordingSleeper:
    def __init__(self):
        self.values = []

    def __call__(self, seconds):
        self.values.append(seconds)


def test_cli_preserves_production_backoff_default():
    parsed = build_argument_parser().parse_args([])
    assert parsed.retry_backoff_seconds == 1.0


def test_cli_allows_zero_backoff_experiment():
    parsed = build_argument_parser().parse_args(
        ["--retry-backoff-seconds", "0"]
    )
    assert parsed.retry_backoff_seconds == 0.0


def test_zero_backoff_does_not_sleep_before_retry(tmp_path: Path):
    sleeper = RecordingSleeper()
    metrics_path = tmp_path / "metrics.json"

    collector = KabuStationUniverseDailyBarCollector(
        client=RetryClient(),
        database_path=Path("unused.db"),
        repository=FakeRepository(),
        request_interval_seconds=0,
        retry_backoff_seconds=0,
        sleeper=sleeper,
        maximum_attempts=3,
        metrics_report_path=metrics_path,
        parallel_workers=1,
    )

    result = collector.collect(
        trading_date=date(2026, 9, 4),
        codes=("1111",),
    )

    assert result.collected_count == 1
    assert sleeper.values == []

    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert payload["retry_backoff_seconds"] == 0
    assert payload["estimated_retry_backoff_budget_seconds"] == 0
    assert payload["metrics"]["retry_attempt_count"] == 1


def test_one_second_backoff_is_reported_and_used(tmp_path: Path):
    sleeper = RecordingSleeper()
    metrics_path = tmp_path / "metrics.json"

    collector = KabuStationUniverseDailyBarCollector(
        client=RetryClient(),
        database_path=Path("unused.db"),
        repository=FakeRepository(),
        request_interval_seconds=0,
        retry_backoff_seconds=1.0,
        sleeper=sleeper,
        maximum_attempts=3,
        metrics_report_path=metrics_path,
        parallel_workers=1,
    )

    result = collector.collect(
        trading_date=date(2026, 9, 4),
        codes=("1111",),
    )

    assert result.collected_count == 1
    assert sleeper.values == [1.0]

    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert payload["retry_backoff_seconds"] == 1.0
    assert payload["estimated_retry_backoff_budget_seconds"] == 1.0
    assert payload["metrics"]["retry_attempt_count"] == 1
