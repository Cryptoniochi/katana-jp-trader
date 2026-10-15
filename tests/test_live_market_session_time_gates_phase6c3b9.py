from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.live.live_production_composition import ConcreteLiveProductionApplication

JST=ZoneInfo("Asia/Tokyo")
DAY=date(2026,10,16)


class Clock:
    def __init__(self, when):
        self.when=when
    def now(self):
        return self.when
    def sleep(self, seconds):
        self.when += timedelta(seconds=seconds)


class Market:
    def __init__(self):
        self.started=[]
        self.stopped=0
    def start(self, codes):
        self.started.append(tuple(codes))
    def stop(self):
        self.stopped += 1


class Session:
    def __init__(self):
        self.heartbeats=0
        self.cycles=[]
    def start(self): pass
    def stop(self): pass
    def record_heartbeat(self): self.heartbeats += 1
    def record_cycle(self, *, successful): self.cycles.append(successful)


class App:
    def __init__(self):
        self.calls=0
    def run_cycle(self, *, trading_date):
        self.calls += 1
        return SimpleNamespace(decision=SimpleNamespace(value="complete"))


class Eod:
    def __init__(self, decisions):
        self.decisions=list(decisions)
        self.calls=0
    def submit_all(self, *, trading_date):
        self.calls += 1
        value=self.decisions.pop(0) if self.decisions else "blocked"
        return SimpleNamespace(decision=SimpleNamespace(value=value))


def build(clock, *, eod):
    app=App()
    obj=ConcreteLiveProductionApplication(
        application=app,
        market_service=Market(),
        session_service=Session(),
        trading_date=DAY,
        cycle_interval_seconds=30,
        eod_liquidation_flow=eod,
        registration_codes=("3911",),
        now_provider=clock.now,
        sleeper=clock.sleep,
    )
    return obj, app


def test_0845_to_0900_never_runs_live_entry_cycle():
    clock=Clock(datetime(2026,10,16,8,45,tzinfo=JST))
    eod=Eod(["complete"])
    obj,app=build(clock,eod=eod)

    # End shortly after the first eligible 09:00 cycle.
    original_sleep=clock.sleep
    def sleep(seconds):
        original_sleep(seconds)
        if app.calls:
            clock.when=datetime(2026,10,16,15,30,tzinfo=JST)
    obj.sleeper=sleep

    assert obj.run()==0
    assert app.calls==1
    assert obj.session_service.heartbeats >= 31


def test_lunch_never_runs_live_entry_cycle():
    clock=Clock(datetime(2026,10,16,11,30,tzinfo=JST))
    eod=Eod(["complete"])
    obj,app=build(clock,eod=eod)
    def sleep(seconds):
        clock.when=datetime(2026,10,16,15,30,tzinfo=JST)
    obj.sleeper=sleep
    assert obj.run()==0
    assert app.calls==0


def test_eod_retries_blocked_until_authoritative_complete_before_1535():
    clock=Clock(datetime(2026,10,16,15,30,tzinfo=JST))
    eod=Eod(["blocked","blocked","complete"])
    obj,app=build(clock,eod=eod)
    assert obj.run()==0
    assert app.calls==0
    assert eod.calls==3
    assert clock.when < datetime(2026,10,16,15,35,tzinfo=JST)


def test_eod_fails_closed_at_1535_if_not_flat():
    clock=Clock(datetime(2026,10,16,15,34,30,tzinfo=JST))
    eod=Eod(["blocked","blocked"])
    obj,app=build(clock,eod=eod)
    assert obj.run()==1
    assert eod.calls==2
    assert clock.when >= datetime(2026,10,16,15,35,tzinfo=JST)
