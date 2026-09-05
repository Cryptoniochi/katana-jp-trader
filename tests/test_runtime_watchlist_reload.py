"""Sprint 135-1: runtime watchlist reload tests."""

from pathlib import Path
from types import SimpleNamespace
import pytest
from app.runtime.paper_trading_composition import (
    RuntimeWatchlistCycleRunner,
    RuntimeWatchlistSynchronizer,
)

class FakeTradingLoop:
    def __init__(self, codes=("1111",)):
        self.codes = tuple(codes)
        self.update_calls = []
    def update_codes(self, codes):
        self.codes = tuple(codes)
        self.update_calls.append(self.codes)
        return self.codes
    def run_cycle(self):
        return "cycle-result"

class FakeKabuService:
    def __init__(self, codes=("1111",), fail=False):
        self.registered_codes = tuple(codes)
        self.calls = []
        self.fail = fail
    def update_registered_codes(self, codes):
        resolved = tuple(codes)
        self.calls.append(resolved)
        if self.fail:
            raise RuntimeError("registration failed")
        self.registered_codes = resolved
        return resolved

class FakeBroker:
    def __init__(self, position_codes=()):
        self.position_codes = tuple(position_codes)
    def list_positions(self):
        return tuple(SimpleNamespace(code=c) for c in self.position_codes)

def write_watchlist(path: Path, codes):
    path.write_text("\n".join(codes) + "\n", encoding="utf-8")

def make_sync(tmp_path, *, initial=("1111",), positions=(), fail=False):
    path = tmp_path / "watchlist.txt"
    write_watchlist(path, initial)
    loop = FakeTradingLoop(initial)
    kabu = FakeKabuService(initial, fail=fail)
    sync = RuntimeWatchlistSynchronizer(
        watchlist_path=path,
        trading_loop_component=loop,
        kabu_station_service=kabu,
        paper_broker=FakeBroker(positions),
        maximum_registered_symbols=50,
    )
    return path, loop, kabu, sync

def test_changed_watchlist_updates_runtime(tmp_path):
    path, loop, kabu, sync = make_sync(tmp_path)
    sync.synchronize()
    kabu.calls.clear(); loop.update_calls.clear()
    write_watchlist(path, ("2222", "3333"))
    assert sync.synchronize() == ("2222", "3333")
    assert kabu.calls == [("2222", "3333")]
    assert loop.update_calls == [("2222", "3333")]

def test_unchanged_watchlist_does_not_reregister(tmp_path):
    _, loop, kabu, sync = make_sync(tmp_path)
    sync.synchronize()
    kabu.calls.clear(); loop.update_calls.clear()
    assert sync.synchronize() == ("1111",)
    assert kabu.calls == []
    assert loop.update_calls == []

def test_positions_have_priority(tmp_path):
    _, _, _, sync = make_sync(
        tmp_path, initial=("1111", "2222"), positions=("9999",)
    )
    assert sync.synchronize()[:3] == ("9999", "1111", "2222")

def test_runtime_universe_is_capped(tmp_path):
    initial = tuple(str(1000 + i) for i in range(50))
    _, _, _, sync = make_sync(
        tmp_path, initial=initial, positions=("9999", "9998")
    )
    result = sync.synchronize()
    assert len(result) == 50
    assert result[:4] == ("9999", "9998", "1000", "1001")
    assert result[-1] == "1047"

def test_duplicates_are_removed(tmp_path):
    _, _, _, sync = make_sync(
        tmp_path, initial=("1111", "2222"), positions=("2222",)
    )
    assert sync.synchronize() == ("2222", "1111")

def test_registration_failure_does_not_update_loop(tmp_path):
    _, loop, _, sync = make_sync(tmp_path, fail=True)
    with pytest.raises(RuntimeError, match="registration failed"):
        sync.synchronize()
    assert loop.codes == ("1111",)
    assert loop.update_calls == []

def test_empty_watchlist_keeps_current_universe(tmp_path):
    path, loop, kabu, sync = make_sync(tmp_path)
    path.write_text("", encoding="utf-8")
    assert sync.synchronize() == ("1111",)
    assert kabu.calls == []
    assert loop.update_calls == []

def test_cycle_runner_synchronizes_before_cycle():
    events = []
    class Sync:
        def synchronize(self): events.append("sync")
    class Loop:
        def run_cycle(self):
            events.append("cycle")
            return "ok"
    runner = RuntimeWatchlistCycleRunner(
        cycle_runner=Loop(), synchronizer=Sync()
    )
    assert runner.run_cycle() == "ok"
    assert events == ["sync", "cycle"]


def test_missing_watchlist_keeps_current_universe(tmp_path):
    path, loop, kabu, sync = make_sync(tmp_path)
    path.unlink()

    assert sync.synchronize() == ("1111",)
    assert kabu.calls == []
    assert loop.update_calls == []


def test_invalid_watchlist_keeps_current_universe(tmp_path):
    path, loop, kabu, sync = make_sync(tmp_path)
    path.write_text("INVALID\n", encoding="utf-8")

    assert sync.synchronize() == ("1111",)
    assert kabu.calls == []
    assert loop.update_calls == []
