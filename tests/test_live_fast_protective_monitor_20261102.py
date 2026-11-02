from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.live.execution_mode import (
    ExecutionModeSettings,
    TradingExecutionMode,
)
from app.live.live_production_runner import (
    LiveCycleDecision,
    LiveProductionRunner,
)
from app.live.live_production_composition import (
    ConcreteLiveProductionApplication,
)


DAY = date(2026, 11, 2)
JST = ZoneInfo("Asia/Tokyo")


class AuthorizedPolicy:
    def require_authorized(self, settings, *, trading_date):
        return None


def test_protective_only_cycle_never_evaluates_strategy_or_submits_buy():
    events = []

    runner = LiveProductionRunner(
        execution_settings=ExecutionModeSettings(
            mode=TradingExecutionMode.LIVE,
            live_armed=True,
            live_confirmation="KATANA-LIVE-2026-11-02",
        ),
        entry_intent_provider=lambda: events.append("strategy") or (),
        entry_submitter=lambda intent, trading_date: events.append("buy"),
        reconciliation_cycle=lambda day: events.append("reconcile")
        or SimpleNamespace(blocked=0),
        position_protection_reconciliation=lambda day: events.append(
            "position"
        )
        or SimpleNamespace(blocked=0),
        protective_cycle=lambda day: events.append("protective")
        or SimpleNamespace(blocked=0),
        arming_policy=AuthorizedPolicy(),
    )

    result = runner.run_protective_cycle(trading_date=DAY)

    assert result.decision is LiveCycleDecision.NO_ACTION
    assert events == ["reconcile", "position", "protective"]


def test_protective_only_cycle_fails_closed_before_stop_when_reconciliation_blocks():
    events = []

    runner = LiveProductionRunner(
        execution_settings=ExecutionModeSettings(
            mode=TradingExecutionMode.LIVE,
            live_armed=True,
            live_confirmation="KATANA-LIVE-2026-11-02",
        ),
        entry_intent_provider=lambda: events.append("strategy") or (),
        entry_submitter=lambda intent, trading_date: events.append("buy"),
        reconciliation_cycle=lambda day: events.append("reconcile")
        or SimpleNamespace(blocked=1),
        position_protection_reconciliation=lambda day: events.append(
            "position"
        )
        or SimpleNamespace(blocked=0),
        protective_cycle=lambda day: events.append("protective")
        or SimpleNamespace(blocked=0),
        arming_policy=AuthorizedPolicy(),
    )

    result = runner.run_protective_cycle(trading_date=DAY)

    assert result.decision is LiveCycleDecision.BLOCKED
    assert events == ["reconcile"]


class Clock:
    def __init__(self, when):
        self.when = when

    def now(self):
        return self.when

    def sleep(self, seconds):
        self.when += timedelta(seconds=seconds)


class Application:
    def __init__(self):
        self.normal_calls = 0
        self.protective_calls = 0

    def run_cycle(self, *, trading_date):
        self.normal_calls += 1
        return SimpleNamespace(
            decision=SimpleNamespace(value="no_action")
        )

    def run_protective_cycle(self, *, trading_date):
        self.protective_calls += 1
        return SimpleNamespace(
            decision=SimpleNamespace(value="no_action")
        )


class Market:
    def start(self, codes):
        pass

    def stop(self):
        pass


class Session:
    def __init__(self, clock):
        self.clock = clock
        self.last_cycle_at = clock.now()
        self.cycles = []
        self.heartbeats = 0

    def start(self):
        pass

    def stop(self):
        pass

    def record_heartbeat(self):
        self.heartbeats += 1

    def record_cycle(self, *, successful):
        self.cycles.append(successful)
        self.last_cycle_at = self.clock.now()

    def snapshot(self):
        return SimpleNamespace(last_cycle_at=self.last_cycle_at)


class Eod:
    def submit_all(self, *, trading_date):
        return SimpleNamespace(
            decision=SimpleNamespace(value="complete")
        )


def test_wait_interval_runs_protection_every_two_seconds_without_strategy():
    clock = Clock(datetime(2026, 11, 2, 10, 0, tzinfo=JST))
    application = Application()

    runtime = ConcreteLiveProductionApplication(
        application=application,
        market_service=Market(),
        session_service=Session(clock),
        trading_date=DAY,
        cycle_interval_seconds=30,
        eod_liquidation_flow=Eod(),
        registration_codes=("7157",),
        now_provider=clock.now,
        sleeper=clock.sleep,
    )

    runtime._wait_with_protection(started_at=clock.now())

    assert application.normal_calls == 0
    assert application.protective_calls == 14
    assert clock.now() == datetime(2026, 11, 2, 10, 0, 30, tzinfo=JST)


def test_wait_interval_stops_protective_polling_at_1515_drain_boundary():
    clock = Clock(datetime(2026, 11, 2, 15, 14, 58, tzinfo=JST))
    application = Application()

    runtime = ConcreteLiveProductionApplication(
        application=application,
        market_service=Market(),
        session_service=Session(clock),
        trading_date=DAY,
        cycle_interval_seconds=30,
        eod_liquidation_flow=Eod(),
        registration_codes=("7157",),
        now_provider=clock.now,
        sleeper=clock.sleep,
    )

    runtime._wait_with_protection(started_at=clock.now())

    assert application.normal_calls == 0
    assert application.protective_calls == 0
    assert clock.now() == datetime(2026, 11, 2, 15, 15, tzinfo=JST)
