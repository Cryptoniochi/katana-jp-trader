from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.live.live_production_composition import ConcreteLiveProductionApplication


JST = ZoneInfo("Asia/Tokyo")
DAY = date(2026, 10, 16)


class Clock:
    def __init__(self, when):
        self.when = when

    def now(self):
        return self.when

    def sleep(self, seconds):
        self.when += timedelta(seconds=seconds)


class Market:
    def __init__(self):
        self.started = []
        self.stopped = 0

    def start(self, codes):
        self.started.append(tuple(codes))

    def stop(self):
        self.stopped += 1


class Session:
    def __init__(self, *, last_cycle_at=None):
        self.heartbeats = 0
        self.cycles = []
        self.last_cycle_at = last_cycle_at

    def start(self):
        pass

    def stop(self):
        pass

    def record_heartbeat(self):
        self.heartbeats += 1

    def record_cycle(self, *, successful):
        self.cycles.append(successful)
        self.last_cycle_at = CURRENT_CLOCK.now()

    def snapshot(self):
        return SimpleNamespace(last_cycle_at=self.last_cycle_at)


class App:
    def __init__(self):
        self.calls = 0

    def run_cycle(self, *, trading_date):
        self.calls += 1
        return SimpleNamespace(decision=SimpleNamespace(value="complete"))


class Eod:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = 0

    def submit_all(self, *, trading_date):
        self.calls += 1
        value = self.decisions.pop(0) if self.decisions else "blocked"
        return SimpleNamespace(decision=SimpleNamespace(value=value))


CURRENT_CLOCK = None


def build(clock, *, eod, last_cycle_at=None):
    global CURRENT_CLOCK
    CURRENT_CLOCK = clock
    app = App()
    obj = ConcreteLiveProductionApplication(
        application=app,
        market_service=Market(),
        session_service=Session(last_cycle_at=last_cycle_at),
        trading_date=DAY,
        cycle_interval_seconds=30,
        eod_liquidation_flow=eod,
        registration_codes=("3911",),
        now_provider=clock.now,
        sleeper=clock.sleep,
    )
    return obj, app


def test_0845_to_0900_never_runs_live_entry_cycle():
    clock = Clock(datetime(2026, 10, 16, 8, 45, tzinfo=JST))
    eod = Eod(["complete"])
    obj, app = build(clock, eod=eod)

    original_sleep = clock.sleep

    def sleep(seconds):
        original_sleep(seconds)
        if app.calls:
            clock.when = datetime(2026, 10, 16, 15, 30, tzinfo=JST)

    obj.sleeper = sleep

    assert obj.run() == 0
    assert app.calls == 1
    assert obj.session_service.heartbeats >= 31


def test_lunch_never_runs_live_entry_cycle():
    clock = Clock(datetime(2026, 10, 16, 11, 30, tzinfo=JST))
    eod = Eod(["complete"])
    obj, app = build(clock, eod=eod)

    def sleep(seconds):
        clock.when = datetime(2026, 10, 16, 15, 30, tzinfo=JST)

    obj.sleeper = sleep
    assert obj.run() == 0
    assert app.calls == 0


def test_first_market_cycle_primes_runtime_health_before_live_cycle():
    clock = Clock(datetime(2026, 10, 16, 10, 0, tzinfo=JST))
    eod = Eod(["complete"])
    obj, app = build(clock, eod=eod)

    def sleep(seconds):
        clock.when = datetime(2026, 10, 16, 15, 30, tzinfo=JST)

    obj.sleeper = sleep

    assert obj.run() == 0
    assert app.calls == 1
    assert obj.session_service.cycles == [True, True]


def test_lunch_resume_primes_stale_cycle_before_live_cycle():
    clock = Clock(datetime(2026, 10, 16, 12, 30, tzinfo=JST))
    old_cycle = datetime(2026, 10, 16, 11, 29, 30, tzinfo=JST)
    eod = Eod(["complete"])
    obj, app = build(clock, eod=eod, last_cycle_at=old_cycle)

    def sleep(seconds):
        clock.when = datetime(2026, 10, 16, 15, 30, tzinfo=JST)

    obj.sleeper = sleep

    assert obj.run() == 0
    assert app.calls == 1
    assert obj.session_service.cycles == [True, True]


def test_fresh_cycle_does_not_add_bootstrap_cycle():
    clock = Clock(datetime(2026, 10, 16, 10, 0, tzinfo=JST))
    fresh_cycle = datetime(2026, 10, 16, 9, 59, 30, tzinfo=JST)
    eod = Eod(["complete"])
    obj, app = build(clock, eod=eod, last_cycle_at=fresh_cycle)

    def sleep(seconds):
        clock.when = datetime(2026, 10, 16, 15, 30, tzinfo=JST)

    obj.sleeper = sleep

    assert obj.run() == 0
    assert app.calls == 1
    assert obj.session_service.cycles == [True]


def test_eod_retries_blocked_until_authoritative_complete_before_1530():
    clock = Clock(datetime(2026, 10, 16, 15, 25, tzinfo=JST))
    eod = Eod(["blocked", "blocked", "complete"])
    obj, app = build(clock, eod=eod)
    assert obj.run() == 0
    assert app.calls == 0
    assert eod.calls == 3
    assert clock.when < datetime(2026, 10, 16, 15, 30, tzinfo=JST)


def test_eod_fails_closed_at_1530_if_not_flat():
    clock = Clock(datetime(2026, 10, 16, 15, 29, 30, tzinfo=JST))
    eod = Eod(["blocked", "blocked"])
    obj, app = build(clock, eod=eod)
    assert obj.run() == 1
    assert eod.calls == 2
    assert clock.when >= datetime(2026, 10, 16, 15, 30, tzinfo=JST)


def test_1520_enters_eod_without_starting_live_entry_cycle():
    clock = Clock(datetime(2026, 10, 16, 15, 20, tzinfo=JST))
    eod = Eod(["complete"])
    obj, app = build(clock, eod=eod)

    assert obj.run() == 0
    assert app.calls == 0
    assert eod.calls == 1


def test_151959_may_run_last_cycle_but_next_iteration_enters_eod():
    clock = Clock(datetime(2026, 10, 16, 15, 19, 59, tzinfo=JST))
    eod = Eod(["complete"])
    obj, app = build(clock, eod=eod)

    original_sleep = clock.sleep

    def sleep(seconds):
        original_sleep(seconds)

    obj.sleeper = sleep

    assert obj.run() == 0
    assert app.calls == 1
    assert eod.calls == 1
    assert clock.when < datetime(2026, 10, 16, 15, 30, tzinfo=JST)
