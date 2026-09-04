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


class SequencedClient:
    def __init__(self, sequences):
        self.settings = SimpleNamespace(
            maximum_registered_symbols=50,
            timeout_seconds=4.0,
        )
        self.sequences = {
            code: list(values)
            for code, values in sequences.items()
        }
        self.calls = []

    def issue_token(self):
        return "token"

    def register_symbols(self, symbols):
        return tuple(symbols)

    def unregister_all(self):
        return None

    def board(self, symbol, *, timeout_seconds=None):
        code = symbol.code
        self.calls.append((code, timeout_seconds))
        outcome = self.sequences[code].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def payload():
    return {
        "OpeningPrice": 100,
        "HighPrice": 110,
        "LowPrice": 95,
        "CurrentPrice": 105,
        "TradingVolume": 1000,
    }


def test_cli_preserves_current_timeout_defaults():
    parsed = build_argument_parser().parse_args([])
    assert parsed.board_first_attempt_timeout_seconds == 0.75
    assert parsed.request_timeout_seconds == 4.0
    assert parsed.parallel_workers == 1


def test_cli_allows_timeout_experiment_values():
    parsed = build_argument_parser().parse_args(
        [
            "--board-first-attempt-timeout-seconds",
            "1.5",
            "--request-timeout-seconds",
            "3.0",
            "--maximum-attempts",
            "2",
        ]
    )
    assert parsed.board_first_attempt_timeout_seconds == 1.5
    assert parsed.request_timeout_seconds == 3.0
    assert parsed.maximum_attempts == 2


def test_attempt_profile_records_each_attempt(tmp_path: Path):
    metrics_path = tmp_path / "metrics.json"
    client = SequencedClient(
        {
            "1111": [TimeoutError("timed out"), payload()],
            "2222": [payload()],
        }
    )

    collector = KabuStationUniverseDailyBarCollector(
        client=client,
        database_path=Path("unused.db"),
        repository=FakeRepository(),
        request_interval_seconds=0,
        retry_backoff_seconds=0,
        maximum_attempts=3,
        metrics_report_path=metrics_path,
        board_first_attempt_timeout_seconds=0.75,
        parallel_workers=1,
    )

    result = collector.collect(
        trading_date=date(2026, 9, 4),
        codes=("1111", "2222"),
    )

    assert result.collected_count == 2

    data = json.loads(metrics_path.read_text(encoding="utf-8"))
    profile = data["attempt_profile"]

    assert len(profile) == 2

    first = profile[0]
    assert first["attempt"] == 1
    assert first["attempt_count"] == 2
    assert first["success_count"] == 1
    assert first["success_ratio"] == 0.5
    assert first["timeout_like_count"] == 1
    assert first["timeout_like_ratio"] == 0.5
    assert first["configured_timeout_seconds"] == 0.75

    second = profile[1]
    assert second["attempt"] == 2
    assert second["attempt_count"] == 1
    assert second["success_count"] == 1
    assert second["success_ratio"] == 1.0
    assert second["timeout_like_count"] == 0
    assert second["configured_timeout_seconds"] == 4.0


def test_first_attempt_timeout_is_passed_to_client(tmp_path: Path):
    client = SequencedClient({"1111": [payload()]})
    collector = KabuStationUniverseDailyBarCollector(
        client=client,
        database_path=Path("unused.db"),
        repository=FakeRepository(),
        request_interval_seconds=0,
        metrics_report_path=tmp_path / "metrics.json",
        board_first_attempt_timeout_seconds=1.25,
    )

    collector.collect(
        trading_date=date(2026, 9, 4),
        codes=("1111",),
    )

    assert client.calls[0] == ("1111", 1.25)
