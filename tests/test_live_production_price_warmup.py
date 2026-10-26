from __future__ import annotations

from datetime import date, datetime, timezone

from app.live.live_production_composition import ConcreteLiveProductionApplication


class _Decision:
    value = "completed"


class _Result:
    decision = _Decision()


class _Application:
    def __init__(self) -> None:
        self.calls = 0

    def run_cycle(self, *, trading_date):
        self.calls += 1
        return _Result()


class _MarketService:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self, codes):
        self.started = True
        return tuple(codes)

    def stop(self):
        self.stopped = True
        return ()


class _Session:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.heartbeats = 0
        self.cycles = 0
        self.last_cycle_at = None

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def record_heartbeat(self):
        self.heartbeats += 1

    def record_cycle(self, *, successful):
        self.cycles += 1
        self.last_cycle_at = datetime(2026, 10, 26, 5, 0, tzinfo=timezone.utc)

    def snapshot(self):
        class Snapshot:
            pass
        snapshot = Snapshot()
        snapshot.last_cycle_at = self.last_cycle_at
        return snapshot


class _Eod:
    def submit_all(self, *, trading_date):
        class Decision:
            value = "complete"
        class Result:
            decision = Decision()
        return Result()


def test_live_cycle_waits_for_first_realtime_push_price() -> None:
    application = _Application()
    market = _MarketService()
    session = _Session()
    ready = {"value": False}
    times = iter(
        (
            datetime(2026, 10, 26, 5, 0, 0, tzinfo=timezone.utc),  # 14:00 JST
            datetime(2026, 10, 26, 5, 0, 1, tzinfo=timezone.utc),
            datetime(2026, 10, 26, 6, 30, 0, tzinfo=timezone.utc),  # 15:30 JST
        )
    )
    sleeps = []

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        ready["value"] = True

    runtime = ConcreteLiveProductionApplication(
        application=application,
        market_service=market,
        session_service=session,
        trading_date=date(2026, 10, 26),
        cycle_interval_seconds=30.0,
        eod_liquidation_flow=_Eod(),
        registration_codes=("4973",),
        realtime_price_ready_provider=lambda: ready["value"],
        now_provider=lambda: next(times),
        sleeper=sleeper,
    )

    assert runtime.run() == 0
    assert market.started is True
    assert market.stopped is True
    assert session.started is True
    assert session.stopped is True
    assert session.heartbeats == 2
    assert application.calls == 1
    assert sleeps[0] == 1.0


def test_live_cycle_never_runs_when_realtime_price_never_arrives() -> None:
    application = _Application()
    market = _MarketService()
    session = _Session()
    times = iter(
        (
            datetime(2026, 10, 26, 5, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 26, 6, 30, 0, tzinfo=timezone.utc),
        )
    )

    runtime = ConcreteLiveProductionApplication(
        application=application,
        market_service=market,
        session_service=session,
        trading_date=date(2026, 10, 26),
        cycle_interval_seconds=30.0,
        eod_liquidation_flow=_Eod(),
        registration_codes=("4973",),
        realtime_price_ready_provider=lambda: False,
        now_provider=lambda: next(times),
        sleeper=lambda _: None,
    )

    assert runtime.run() == 0
    assert application.calls == 0
    assert session.heartbeats == 1
