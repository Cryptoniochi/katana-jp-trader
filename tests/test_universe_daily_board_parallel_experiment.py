import json
import threading
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.run_universe_bootstrap import build_argument_parser
from app.universe.kabu_station_universe_daily_collector import (
    KabuStationUniverseDailyBarCollector,
)


class ThreadAwareRepository:
    def __init__(self):
        self.saved = []
        self.writer_threads = []

    def upsert_many(self, bars):
        values = tuple(bars)
        self.saved.extend(values)
        self.writer_threads.append(threading.get_ident())
        return len(values)


class ConcurrentFakeClient:
    def __init__(self):
        self.settings = SimpleNamespace(
            maximum_registered_symbols=50,
            timeout_seconds=4.0,
        )
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def issue_token(self):
        return "token"

    def unregister_all(self):
        return None

    def register_symbols(self, symbols):
        return tuple(symbols)

    def board(self, symbol, *, timeout_seconds=None):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.05)
            return {
                "OpeningPrice": 100,
                "HighPrice": 110,
                "LowPrice": 95,
                "CurrentPrice": 105,
                "TradingVolume": 1000,
            }
        finally:
            with self.lock:
                self.active -= 1


def test_parallel_workers_default_is_safe_one():
    parsed = build_argument_parser().parse_args([])
    assert parsed.parallel_workers == 1


def test_parallel_workers_two_is_explicit_opt_in():
    parsed = build_argument_parser().parse_args(
        ["--parallel-workers", "2"]
    )
    assert parsed.parallel_workers == 2


def test_two_workers_overlap_board_requests_but_persist_on_main_thread(
    tmp_path: Path,
):
    main_thread = threading.get_ident()
    repository = ThreadAwareRepository()
    client = ConcurrentFakeClient()
    metrics_path = tmp_path / "metrics.json"

    collector = KabuStationUniverseDailyBarCollector(
        client=client,
        database_path=Path("unused.db"),
        repository=repository,
        request_interval_seconds=0,
        retry_backoff_seconds=0,
        metrics_report_path=metrics_path,
        parallel_workers=2,
    )

    result = collector.collect(
        trading_date=date(2026, 9, 4),
        codes=("1111", "2222", "3333", "4444"),
    )

    assert result.collected_count == 4
    assert result.saved_count == 4
    assert client.max_active == 2
    assert repository.writer_threads
    assert set(repository.writer_threads) == {main_thread}

    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert payload["parallel_workers"] == 2
    assert payload["requested_count"] == 4
    assert payload["collected_count"] == 4
    assert payload["metrics"]["first_attempt_count"] == 4
    assert payload["metrics"]["first_attempt_success_count"] == 4
    assert payload["collection_wall_elapsed_seconds"] > 0


def test_one_worker_remains_sequential(tmp_path: Path):
    client = ConcurrentFakeClient()
    collector = KabuStationUniverseDailyBarCollector(
        client=client,
        database_path=Path("unused.db"),
        repository=ThreadAwareRepository(),
        request_interval_seconds=0,
        metrics_report_path=tmp_path / "metrics.json",
        parallel_workers=1,
    )

    result = collector.collect(
        trading_date=date(2026, 9, 4),
        codes=("1111", "2222"),
    )

    assert result.collected_count == 2
    assert client.max_active == 1
